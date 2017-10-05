from symbolic._compat import implements_to_string
from symbolic._lowlevel import lib, ffi
from symbolic.demangle import demangle_symbol
from symbolic.utils import RustObject, rustcall, decode_str, decode_uuid, \
     encode_str, common_path_join, strip_common_path_prefix, encode_path
from symbolic.common import parse_addr
from symbolic import exceptions


__all__ = ['Symbol', 'SymCache', 'find_best_instruction']


# the most recent version for the symcache file format.
SYMCACHE_LATEST_VERSION = rustcall(
    lib.symbolic_symcache_latest_file_format_version)


@implements_to_string
class Symbol(object):

    def __init__(self, sym_addr, instr_addr, line, symbol,
                 filename, base_dir, comp_dir):
        self.sym_addr = sym_addr
        self.instr_addr = instr_addr
        self.line = line
        self.symbol = symbol
        self.filename = filename
        self.base_dir = base_dir
        self.comp_dir = comp_dir

    @property
    def function_name(self):
        """The demangled function name."""
        return demangle_symbol(self.symbol)

    @property
    def abs_path(self):
        """Returns the absolute path."""
        return common_path_join(self.base_dir, self.filename)

    @property
    def rel_path(self):
        """Returns the relative path to the comp dir."""
        return strip_common_path_prefix(self.abs_path, self.comp_dir)

    def __str__(self):
        return '%s:%s (%s)' % (
            self.function_name,
            self.line,
            self.rel_path,
        )

    def __repr__(self):
        return 'Symbol(%s)' % (
            ', '.join('%s=%r' % x for x in sorted(self.__dict__.items()))
        )


class SymCache(RustObject):
    __dealloc_func__ = lib.symbolic_symcache_free

    @classmethod
    def from_path(self, path):
        """Loads a symcache from a file via mmap."""
        return SymCache._from_objptr(
            rustcall(lib.symbolic_symcache_from_path, path))

    @classmethod
    def from_bytes(self, bytes):
        """Loads a symcache from a file via mmap."""
        bytes = memoryview(bytes)
        return SymCache._from_objptr(
            rustcall(lib.symbolic_symcache_from_bytes, bytes, len(bytes)))

    @property
    def arch(self):
        """The architecture of the symcache."""
        # make it an ascii bytestring on 2.x
        return str(decode_str(self._methodcall(lib.symbolic_symcache_get_arch)))

    @property
    def uuid(self):
        """The UUID of the object."""
        return decode_uuid(self._methodcall(lib.symbolic_symcache_get_uuid))

    @property
    def has_line_info(self):
        """Does this file have line information?"""
        return self._methodcall(lib.symbolic_symcache_has_line_info)

    @property
    def has_file_info(self):
        """Does this file have file information?"""
        return self._methodcall(lib.symbolic_symcache_has_file_info)

    @property
    def file_format_version(self):
        """Version of the file format."""
        return self._methodcall(lib.symbolic_symcache_file_format_version)

    @property
    def is_latest_file_format(self):
        """Returns true if this is the latest file format."""
        return self.file_format_version >= SYMCACHE_LATEST_VERSION

    @property
    def buffer(self):
        """Returns the underlying bytes of the cache."""
        buf = self._methodcall(lib.symbolic_symcache_get_bytes)
        size = self._methodcall(lib.symbolic_symcache_get_size)
        return ffi.buffer(buf, size)

    def dump(self, f):
        """Dumps the symcache into a file object."""
        f.write(self.buffer)

    def lookup(self, addr):
        """Look up a single address."""
        addr = parse_addr(addr)
        rv = self._methodcall(lib.symbolic_symcache_lookup, addr)
        try:
            matches = []
            for idx in range(rv.len):
                sym = rv.items[idx]
                matches.append(Symbol(
                    sym_addr=sym.sym_addr,
                    instr_addr=sym.instr_addr,
                    line=sym.line,
                    symbol=decode_str(sym.symbol),
                    filename=decode_str(sym.filename),
                    base_dir=decode_str(sym.base_dir),
                    comp_dir=decode_str(sym.comp_dir),
                ))
        finally:
            rustcall(lib.symbolic_lookup_result_free, ffi.addressof(rv))
        return matches


def find_best_instruction(addr, arch, crashing_frame=False,
                          signal=None, ip_reg=None):
    """Given an instruction and meta data attempts to find the best one
    by using a heuristic we inherited from symsynd.
    """
    addr = parse_addr(addr)
    ii = ffi.new('SymbolicInstructionInfo *')
    ii[0].addr = addr
    ii[0].arch = encode_str(arch)
    ii[0].crashing_frame = crashing_frame
    ii[0].signal = signal or 0
    ii[0].ip_reg = parse_addr(ip_reg)
    try:
        return int(rustcall(lib.symbolic_find_best_instruction, ii))
    except (exceptions.Parse, exceptions.NotFound):
        return int(addr)
