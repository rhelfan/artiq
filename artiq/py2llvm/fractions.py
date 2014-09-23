import inspect
import ast

from llvm import core as lc

from artiq.py2llvm.values import VGeneric
from artiq.py2llvm.base_types import VBool, VInt


def _gcd(a, b):
    if a < 0:
        a = -a
    while a:
        c = a
        a = b % a
        b = c
    return b


def init_module(module):
    func_def = ast.parse(inspect.getsource(_gcd)).body[0]
    module.compile_function(func_def, {"a": VInt(64), "b": VInt(64)})


def _reduce(builder, a, b):
    gcd_f = builder.basic_block.function.module.get_function_named("_gcd")
    gcd = builder.call(gcd_f, [a, b])
    a = builder.sdiv(a, gcd)
    b = builder.sdiv(b, gcd)
    return a, b


def _signnum(builder, a, b):
    function = builder.basic_block.function
    orig_block = builder.basic_block
    swap_block = function.append_basic_block("sn_swap")
    merge_block = function.append_basic_block("sn_merge")

    condition = builder.icmp(
        lc.ICMP_SLT, b, lc.Constant.int(lc.Type.int(64), 0))
    builder.cbranch(condition, swap_block, merge_block)

    builder.position_at_end(swap_block)
    minusone = lc.Constant.int(lc.Type.int(64), -1)
    a_swp = builder.mul(minusone, a)
    b_swp = builder.mul(minusone, b)
    builder.branch(merge_block)

    builder.position_at_end(merge_block)
    a_phi = builder.phi(lc.Type.int(64))
    a_phi.add_incoming(a, orig_block)
    a_phi.add_incoming(a_swp, swap_block)
    b_phi = builder.phi(lc.Type.int(64))
    b_phi.add_incoming(b, orig_block)
    b_phi.add_incoming(b_swp, swap_block)

    return a_phi, b_phi


def _make_ssa(builder, n, d):
    value = lc.Constant.undef(lc.Type.vector(lc.Type.int(64), 2))
    value = builder.insert_element(
        value, n, lc.Constant.int(lc.Type.int(), 0))
    value = builder.insert_element(
        value, d, lc.Constant.int(lc.Type.int(), 1))
    return value


class VFraction(VGeneric):
    def get_llvm_type(self):
        return lc.Type.vector(lc.Type.int(64), 2)

    def _nd(self, builder):
        ssa_value = self.auto_load(builder)
        a = builder.extract_element(
            ssa_value, lc.Constant.int(lc.Type.int(), 0))
        b = builder.extract_element(
            ssa_value, lc.Constant.int(lc.Type.int(), 1))
        return a, b

    def set_value_nd(self, builder, a, b):
        a = a.o_int64(builder).auto_load(builder)
        b = b.o_int64(builder).auto_load(builder)
        a, b = _reduce(builder, a, b)
        a, b = _signnum(builder, a, b)
        self.auto_store(builder, _make_ssa(builder, a, b))

    def set_value(self, builder, v):
        if not isinstance(v, VFraction):
            raise TypeError
        self.auto_store(builder, v.auto_load(builder))

    def o_getattr(self, attr, builder):
        if attr == "numerator":
            idx = 0
        elif attr == "denominator":
            idx = 1
        else:
            raise AttributeError
        r = VInt(64)
        if builder is not None:
            elt = builder.extract_element(
                self.auto_load(builder),
                lc.Constant.int(lc.Type.int(), idx))
            r.auto_store(builder, elt)
        return r

    def o_bool(self, builder):
        r = VBool()
        if builder is not None:
            zero = lc.Constant.int(lc.Type.int(64), 0)
            a = builder.extract_element(
                self.auto_load(builder), lc.Constant.int(lc.Type.int(), 0))
            r.auto_store(builder, builder.icmp(lc.ICMP_NE, a, zero))
        return r

    def o_intx(self, target_bits, builder):
        if builder is None:
            return VInt(target_bits)
        else:
            r = VInt(64)
            a, b = self._nd(builder)
            r.auto_store(builder, builder.sdiv(a, b))
            return r.o_intx(target_bits, builder)

    def o_roundx(self, target_bits, builder):
        if builder is None:
            return VInt(target_bits)
        else:
            r = VInt(64)
            a, b = self._nd(builder)
            h_b = builder.ashr(b, lc.Constant.int(lc.Type.int(64), 1))

            function = builder.basic_block.function
            add_block = function.append_basic_block("fr_add")
            sub_block = function.append_basic_block("fr_sub")
            merge_block = function.append_basic_block("fr_merge")

            condition = builder.icmp(
                lc.ICMP_SLT, a, lc.Constant.int(lc.Type.int(64), 0))
            builder.cbranch(condition, sub_block, add_block)

            builder.position_at_end(add_block)
            a_add = builder.add(a, h_b)
            builder.branch(merge_block)
            builder.position_at_end(sub_block)
            a_sub = builder.sub(a, h_b)
            builder.branch(merge_block)

            builder.position_at_end(merge_block)
            a = builder.phi(lc.Type.int(64))
            a.add_incoming(a_add, add_block)
            a.add_incoming(a_sub, sub_block)
            r.auto_store(builder, builder.sdiv(a, b))
            return r.o_intx(target_bits, builder)

    def _o_eq_inv(self, other, builder, ne):
        if not isinstance(other, (VInt, VFraction)):
            return NotImplemented
        r = VBool()
        if builder is not None:
            if isinstance(other, VInt):
                other = other.o_int64(builder)
                a, b = self._nd(builder)
                ssa_r = builder.and_(
                    builder.icmp(lc.ICMP_EQ, a,
                                 other.auto_load()),
                    builder.icmp(lc.ICMP_EQ, b,
                                 lc.Constant.int(lc.Type.int(64), 1)))
            else:
                a, b = self._nd(builder)
                c, d = other._nd(builder)
                ssa_r = builder.and_(
                    builder.icmp(lc.ICMP_EQ, a, c),
                    builder.icmp(lc.ICMP_EQ, b, d))
            if ne:
                ssa_r = builder.xor(ssa_r,
                                    lc.Constant.int(lc.Type.int(1), 1))
            r.auto_store(builder, ssa_r)
        return r

    def o_eq(self, other, builder):
        return self._o_eq_inv(other, builder, False)

    def o_ne(self, other, builder):
        return self._o_eq_inv(other, builder, True)

    def _o_addsub(self, other, builder, sub, invert=False):
        if not isinstance(other, (VInt, VFraction)):
            return NotImplemented
        r = VFraction()
        if builder is not None:
            if isinstance(other, VInt):
                i = other.o_int64(builder).auto_load(builder)
                x, rd = self._nd(builder)
                y = builder.mul(rd, i)
            else:
                a, b = self._nd(builder)
                c, d = other._nd(builder)
                rd = builder.mul(b, d)
                x = builder.mul(a, d)
                y = builder.mul(c, b)
            if sub:
                if invert:
                    rn = builder.sub(y, x)
                else:
                    rn = builder.sub(x, y)
            else:
                rn = builder.add(x, y)
            rn, rd = _reduce(builder, rn, rd)  # rd is already > 0
            r.auto_store(builder, _make_ssa(builder, rn, rd))
        return r

    def o_add(self, other, builder):
        return self._o_addsub(other, builder, False)

    def o_sub(self, other, builder):
        return self._o_addsub(other, builder, True)

    def or_add(self, other, builder):
        return self._o_addsub(other, builder, False)

    def or_sub(self, other, builder):
        return self._o_addsub(other, builder, True, True)

    def _o_muldiv(self, other, builder, div, invert=False):
        if not isinstance(other, (VFraction, VInt)):
            return NotImplemented
        r = VFraction()
        if builder is not None:
            a, b = self._nd(builder)
            if invert:
                a, b = b, a
            if isinstance(other, VInt):
                i = other.o_int64(builder).auto_load(builder)
                if div:
                    b = builder.mul(b, i)
                else:
                    a = builder.mul(a, i)
            else:
                c, d = other._nd(builder)
                if div:
                    a = builder.mul(a, d)
                    b = builder.mul(b, c)
                else:
                    a = builder.mul(a, c)
                    b = builder.mul(b, d)
            if div or invert:
                a, b = _signnum(builder, a, b)
            a, b = _reduce(builder, a, b)
            r.auto_store(builder, _make_ssa(builder, a, b))
        return r

    def o_mul(self, other, builder):
        return self._o_muldiv(other, builder, False)

    def o_truediv(self, other, builder):
        return self._o_muldiv(other, builder, True)

    def or_mul(self, other, builder):
        return self._o_muldiv(other, builder, False)

    def or_truediv(self, other, builder):
        return self._o_muldiv(other, builder, False, True)

    def o_floordiv(self, other, builder):
        r = self.o_truediv(other, builder)
        if r is NotImplemented:
            return r
        else:
            return r.o_int(builder)

    def or_floordiv(self, other, builder):
        r = self.or_truediv(other, builder)
        if r is NotImplemented:
            return r
        else:
            return r.o_int(builder)