# -*- coding: utf-8 -*-
from __future__ import division
import traceback
import math

from Autodesk.Revit.DB import *
from pyrevit import revit, forms

# ============================================================
# MODE
# ============================================================
DEBUG = True
# 0=最小, 1=通常, 2=全部
DEBUG_LEVEL = 2

# ログが重すぎる時の安全弁（最初のN本だけログ）
# 全部出したいなら None にする
DEBUG_MAX = None   # 例: 20 / None

# ============================================================
# SETTINGS
# ============================================================
# 現状X方向のみサポート 人間から見て左をi 右をjとする
# 将来Y方向サポート予定
DEBUG_ONLY = False
SEARCH_MM  = 2000
ROUND_COL_MM = 100.0
ONLY_STRUCTURAL_FRAMING = False

P_BEAM_LEN = u"L"
P_I_COL  = u"i側柱サイズ"
P_J_COL  = u"j側柱サイズ"
P_BASE_W = u"Base_W"

P_ANGLE     = u"angle"
P_END_ANGLE = u"End_angle"

P_IW_R2   = u"iw_R2"
P_IW_L2   = u"iw_L2"
P_I_TAPER = u"i_taper_dist"
P_I_CENTER    = u"i_center_offset"
P_I_TAPER_OFF = u"i_taper_offset"
P_I_COL_OFFSET = u"i_column_offset"

P_JW_R2   = u"jw_R2"
P_JW_L2   = u"jw_L2"
P_J_TAPER = u"j_taper_dist"
P_J_CENTER    = u"j_center_offset"
P_J_TAPER_OFF = u"j_taper_offset"


# ============================================================
# DEBUG UTIL
# ============================================================
def vstr(v):
    try:
        if v is None: return "None"
        return "({:.4f},{:.4f},{:.4f})".format(v.X, v.Y, v.Z)
    except:
        return str(v)

def fstr(x):
    try:
        if x is None: return "None"
        return "{:.6f}".format(float(x))
    except:
        return str(x)

def log(s):
    # pyRevitなら print が Output に流れる
    print(s)

class DebugCtx(object):
    """
    - enabled=Falseなら全てno-op
    - set()で値を貯める
    - dump()で最後に一気に吐く
    - section()でカテゴリごとにまとまる
    """
    def __init__(self, enabled, level=1, header=None):
        self.enabled = enabled
        self.level = level
        self.header = header or ""
        self._sec = None
        self._data = []   # list of (sec, key, val)

    def section(self, name):
        if not self.enabled: return
        self._sec = name

    def set(self, key, val, min_level=1):
        if (not self.enabled) or (self.level < min_level):
            return
        sec = self._sec or "misc"
        self._data.append((sec, key, val))

    def exc(self, ex, where=""):
        if not self.enabled: return
        sec = "exception"
        msg = "{}: {}".format(where, ex) if where else str(ex)
        self._data.append((sec, "message", msg))
        self._data.append((sec, "traceback", traceback.format_exc()))

    def dump(self, logfn):
        if not self.enabled:
            return
        logfn("==== DEBUG START {} ====".format(self.header))

        by = {}
        for sec, k, v in self._data:
            by.setdefault(sec, []).append((k, v))

        for sec in sorted(by.keys()):
            logfn("[{}]".format(sec))
            for k, v in sorted(by[sec], key=lambda t: t[0]):
                try:
                    vs = v if isinstance(v, basestring) else str(v)
                except:
                    vs = "<unprintable>"

                if vs is None:
                    logfn("  {} = None".format(k))
                elif "\n" in vs:
                    logfn("  {} =".format(k))
                    for line in vs.splitlines():
                        logfn("    " + line)
                else:
                    logfn("  {} = {}".format(k, vs))

        logfn("==== DEBUG END {} ====".format(self.header))


# ============================================================
# UTILS
# ============================================================
def mm_to_ft(mm): return mm / 304.8
def ft_to_mm(ft): return ft * 304.8

def dot(a, b): return a.X*b.X + a.Y*b.Y + a.Z*b.Z
def clamp(x, lo, hi): return max(lo, min(hi, x))

def to_xy(p): return XYZ(p.X, p.Y, 0.0)

def unit_xy(v):
    v2 = XYZ(v.X, v.Y, 0.0)
    if v2.GetLength() < 1e-9:
        return None
    return v2.Normalize()

def perp_xy(ex):
    return XYZ(-ex.Y, ex.X, 0.0)

def normalize_angle_pm90(a):
    """角度a(rad)を[-90°, +90°]に正規化（ex と -ex を同一視）"""
    while a <= -math.pi/2.0:
        a += math.pi
    while a > math.pi/2.0:
        a -= math.pi
    return a

def get_param(elem, name):
    return elem.LookupParameter(name) if name else None

def get_double(elem, name):
    p = get_param(elem, name)
    if p is None:
        return None, u"Param not found: {0}".format(name)
    if p.StorageType != StorageType.Double:
        return None, u"Param not double: {0} ({1})".format(name, p.StorageType)
    return p.AsDouble(), None

def set_double(elem, name, value):
    if not name:
        return None
    p = get_param(elem, name)
    if p is None:
        return u"Param not found: {0}".format(name)
    if p.IsReadOnly:
        return u"Param read-only: {0}".format(name)
    if p.StorageType != StorageType.Double:
        return u"Param not double: {0} ({1})".format(name, p.StorageType)
    p.Set(value)
    return None

def get_len_inst_or_type(elem, pname):
    # instance
    try:
        p = elem.LookupParameter(pname)
        if p and p.StorageType == StorageType.Double:
            return p.AsDouble()
    except:
        pass
    # type
    try:
        sym = elem.Symbol
        if sym:
            p = sym.LookupParameter(pname)
            if p and p.StorageType == StorageType.Double:
                return p.AsDouble()
    except:
        pass
    return None

def get_base_w(fi):
    w, err = get_double(fi, P_BASE_W)
    if not err:
        return w, None
    sym = fi.Symbol
    w, err2 = get_double(sym, P_BASE_W)
    if not err2:
        return w, None
    return None, u"{0} missing (instance/type)".format(P_BASE_W)

def signed_view_angle_rad(ex, view):
    """ビュー基準の符号付き角（Right=0°, Up=+90°）"""
    vr = unit_xy(view.RightDirection)
    vu = unit_xy(view.UpDirection)
    ex2 = unit_xy(ex)
    if vr is None or vu is None or ex2 is None:
        return 0.0
    return math.atan2(dot(ex2, vu), dot(ex2, vr))

def compute_end_angle_signed_from_ang(ang_norm):
    """
    ang>=0 -> 鋭角側(<=90)
    ang<0  -> 鈍角側(>90)
    ※ang は必ず [-90,+90] に正規化済み
    """
    a = abs(ang_norm)
    if ang_norm >= 0:
        end = (math.pi/2.0) - a
    else:
        end = (math.pi/2.0) + a
    return clamp(end, math.radians(1.0), math.radians(179.0))

def ceil_mm_to_ft(x_ft, step_mm=10.0):
    x_mm = ft_to_mm(x_ft)
    x_mm_ceil = step_mm * math.ceil(x_mm / step_mm)
    return mm_to_ft(x_mm_ceil)

# --- 柱中心（XY） ---
def col_center_xy(col):
    try:
        loc = col.Location
        if isinstance(loc, LocationPoint):
            p = loc.Point
            return XYZ(p.X, p.Y, 0.0)
    except:
        pass
    bb = col.get_BoundingBox(None)
    if bb is None:
        return None
    return XYZ((bb.Min.X + bb.Max.X)*0.5, (bb.Min.Y + bb.Max.Y)*0.5, 0.0)

# --- 柱探索（BBox平面距離） ---
def dist2_point_to_bb_xy(pt, bb):
    mn, mx = bb.Min, bb.Max
    dx = 0.0
    if pt.X < mn.X: dx = mn.X - pt.X
    elif pt.X > mx.X: dx = pt.X - mx.X

    dy = 0.0
    if pt.Y < mn.Y: dy = mn.Y - pt.Y
    elif pt.Y > mx.Y: dy = pt.Y - mx.Y
    return dx*dx + dy*dy

def nearest_column(doc, pt, radius_ft):
    cols = (FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_StructuralColumns)
            .WhereElementIsNotElementType()
            .ToElements())

    best = None
    best_d2 = radius_ft * radius_ft
    z_tol = mm_to_ft(2000)

    for c in cols:
        bb = c.get_BoundingBox(None)
        if bb is None:
            continue
        if pt.Z < bb.Min.Z - z_tol or pt.Z > bb.Max.Z + z_tol:
            continue
        d2 = dist2_point_to_bb_xy(pt, bb)
        if d2 < best_d2:
            best_d2 = d2
            best = c

    return best, best_d2

def get_col_bd(col):
    sym = col.Symbol if col else None
    if sym is None:
        return None, None, None, None  # B, D, Bsrc, Dsrc

    def getd(name):
        p = sym.LookupParameter(name)
        if p and p.StorageType == StorageType.Double:
            return p.AsDouble()
        return None

    B = getd(u"B")
    if B is None:
        return None, None, None, None
    Bsrc = u"B"

    D = getd(u"D")
    Dsrc = u"D" if D is not None else None
    if D is None:
        D = getd(u"D1"); Dsrc = u"D1" if D is not None else None
    if D is None:
        D = getd(u"Bwo"); Dsrc = u"Bwo" if D is not None else None
    if D is None:
        D = B; Dsrc = u"(fallback B)"

    return B, D, Bsrc, Dsrc

def fmt_halves_origin(side, col, B, D, Bsrc, Dsrc):
    cid = col.Id.IntegerValue if col else None
    return u"\n".join([
        u"[{}] colId={}".format(side, cid),
        u"[{}] B({})={:.3f}mm  D({})={:.3f}mm".format(side, Bsrc, ft_to_mm(B), Dsrc, ft_to_mm(D)),
        u"[{}] half_center = D/2 = {:.3f}/2 = {:.3f}mm".format(side, ft_to_mm(D), ft_to_mm(0.5*D)),
        u"[{}] half_iw     = B/2 = {:.3f}/2 = {:.3f}mm".format(side, ft_to_mm(B), ft_to_mm(0.5*B)),
    ])


def column_face_size_from_type(col, ey):
    """梁左右(ey)方向に見た柱の素の見かけ幅（フカシ無し）"""
    B, D, _, _ = get_col_bd(col)
    if B is None or D is None:
        return None
    try:
        t = col.GetTransform()
        cx = unit_xy(t.BasisX)
        cy = unit_xy(t.BasisY)
    except:
        return max(B, D)

    ey2 = unit_xy(ey)
    if ey2 is None or cx is None or cy is None:
        return max(B, D)

    ax = abs(dot(cx, ey2))
    ay = abs(dot(cy, ey2))
    return D if ax >= ay else B

def get_halves_center_and_iw_LR_with_fukashi(col, ey_axis, fL_name, fR_name, dbg=None, tag=""):
    """
    戻り:
      half_center (=D/2)
      halfL_iw   (=B/2 + fukashi_L)   ※Lは梁+ey側
      halfR_iw   (=B/2 + fukashi_R)   ※Rは梁-ey側

    ※柱のローカル軸(BasisX/BasisY)のどっちがeyに近いかで
      「その軸の+側/-側が梁の+ey/-eyに対応するか」を見て左右を必要なら入替する。
    """
    B, D, Bsrc, Dsrc = get_col_bd(col)
    if B is None or D is None:
        return None, None, None, u"B/D not found"

    half_center = 0.5 * D
    half_iw_base = 0.5 * B  # あなたの前提（iwはB）

    # フカシ（未設定なら0）
    fL = get_len_inst_or_type(col, fL_name) or 0.0
    fR = get_len_inst_or_type(col, fR_name) or 0.0

    # 初期（L=+ey, R=-ey）
    halfL = half_iw_base + fL
    halfR = half_iw_base + fR

    try:
        tr = col.GetTransform()
        cx = unit_xy(tr.BasisX)
        cy = unit_xy(tr.BasisY)
        ey = unit_xy(ey_axis)
    except:
        cx = cy = ey = None

    # 柱の向きが取れないなら、そのまま返す
    if cx is None or cy is None or ey is None:
        if dbg:
            dbg.section("halves.LR")
            dbg.set(tag+"note", "axis unavailable -> no swap", 1)
            dbg.set(tag+"Bsrc", Bsrc, 2)
            dbg.set(tag+"Dsrc", Dsrc, 2)
            dbg.set(tag+"half_center_mm", fstr(ft_to_mm(half_center)), 1)
            dbg.set(tag+"halfL_mm", fstr(ft_to_mm(halfL)), 1)
            dbg.set(tag+"halfR_mm", fstr(ft_to_mm(halfR)), 1)
        return half_center, halfL, halfR, None

    # ey により近い柱軸を採用（符号判定だけに使う）
    ax = abs(dot(cx, ey))
    ay = abs(dot(cy, ey))
    axis = cx if ax >= ay else cy
    s = dot(axis, ey)  # +なら axisが+ey向き、-なら -ey向き

    # axis が -ey 側を向いているなら「L/Rが逆」なのでスワップ
    swapped = False
    if s < 0:
        halfL, halfR = halfR, halfL
        swapped = True

    if dbg:
        dbg.section("halves.LR")
        dbg.set(tag+"Bsrc", Bsrc, 2)
        dbg.set(tag+"Dsrc", Dsrc, 2)
        dbg.set(tag+"ey", vstr(ey), 2)
        dbg.set(tag+"cx", vstr(cx), 2)
        dbg.set(tag+"cy", vstr(cy), 2)
        dbg.set(tag+"ax", fstr(ax), 2)
        dbg.set(tag+"ay", fstr(ay), 2)
        dbg.set(tag+"use_axis", "X" if ax >= ay else "Y", 1)
        dbg.set(tag+"dot(axis,ey)", fstr(s), 1)
        dbg.set(tag+"swapped", str(swapped), 1)
        dbg.set(tag+"half_center_mm", fstr(ft_to_mm(half_center)), 1)
        dbg.set(tag+"fL_name", fL_name, 2)
        dbg.set(tag+"fR_name", fR_name, 2)
        dbg.set(tag+"fL_mm", fstr(ft_to_mm(fL)), 1)
        dbg.set(tag+"fR_mm", fstr(ft_to_mm(fR)), 1)
        dbg.set(tag+"halfL_mm", fstr(ft_to_mm(halfL)), 1)
        dbg.set(tag+"halfR_mm", fstr(ft_to_mm(halfR)), 1)

    return half_center, halfL, halfR, None


def col_hit_face_dist_along_u_Auto(col, uH, view, dbg=None, tag=""):
    """
    柱のローカルX面 or Y面のうち、梁方向uに対して「ちゃんと当たる面」を自動選択して
    面までの距離t（u方向）を返す。
    """
    B, D, _, _ = get_col_bd(col)
    if B is None:
        return None, u"B missing"
    if D is None:
        D = B

    # フカシ（暫定：03/04を両面に流用）
    fU  = get_len_inst_or_type(col, u"フカシ03") or 0.0
    fDk = get_len_inst_or_type(col, u"フカシ04") or 0.0

    try:
        tr = col.GetTransform()
        cx = unit_xy(tr.BasisX)
        cy = unit_xy(tr.BasisY)
    except:
        return None, u"GetTransform fail"

    u = unit_xy(uH)
    if cx is None or cy is None or u is None:
        return None, u"axis normalize fail"

    ux = dot(u, cx)
    uy = dot(u, cy)

    # ★当てる面を選ぶ（平行に近い方を避ける）
    use_axis = "X" if abs(ux) >= abs(uy) else "Y"
    n = cx if use_axis == "X" else cy
    un = ux if use_axis == "X" else uy

    # 寸法（X面ならB/2、Y面ならD/2 のつもり。逆ならここを入替）
    half_dim = 0.5 * (B if use_axis == "X" else D)

    # ほぼ平行なら失敗扱い
    if abs(un) < 0.02:
        if dbg:
            dbg.section("hit.auto")
            dbg.set(tag+"ux", fstr(ux), 1)
            dbg.set(tag+"uy", fstr(uy), 1)
            dbg.set(tag+"use_axis", use_axis, 1)
        return None, u"u nearly parallel to {} face".format(use_axis)

    # view.Upでフカシの上下を決める（暫定ロジック踏襲）
    vu = unit_xy(view.UpDirection)
    if vu is None:
        f_pos = 0.5*(fU + fDk)
        f_neg = 0.5*(fU + fDk)
    else:
        if dot(n, vu) >= 0:
            f_pos = fU
            f_neg = fDk
        else:
            f_pos = fDk
            f_neg = fU

    addUD = (f_pos if un >= 0 else f_neg)
    h = half_dim + addUD
    t = h / abs(un)

    if dbg:
        dbg.section("hit.auto")
        dbg.set(tag+"use_axis", use_axis, 1)
        dbg.set(tag+"u", vstr(u), 2)
        dbg.set(tag+"cx", vstr(cx), 2)
        dbg.set(tag+"cy", vstr(cy), 2)
        dbg.set(tag+"ux", fstr(ux), 1)
        dbg.set(tag+"uy", fstr(uy), 1)
        dbg.set(tag+"half_dim_mm", fstr(ft_to_mm(half_dim)), 1)
        dbg.set(tag+"addUD_mm", fstr(ft_to_mm(addUD)), 1)
        dbg.set(tag+"h_mm", fstr(ft_to_mm(h)), 1)
        dbg.set(tag+"t_mm", fstr(ft_to_mm(t)), 1)

    return t, None


# def col_hit_face_dist_along_u_Yonly(col, uH, view, dbg=None, tag=""):
#     """
#     暫定仕様：柱の「Y面（BasisY方向の面）」だけでヒット距離を計算する。
#     """
#     B, D, _, _ = get_col_bd(col)
#     if B is None:
#         return None, u"B missing"
#     if D is None:
#         D = B

#     fU  = get_len_inst_or_type(col, u"フカシ03") or 0.0
#     fDk = get_len_inst_or_type(col, u"フカシ04") or 0.0

#     try:
#         tr = col.GetTransform()
#         cy = unit_xy(tr.BasisY)
#     except:
#         return None, u"GetTransform fail"

#     u = unit_xy(uH)
#     if cy is None or u is None:
#         return None, u"axis normalize fail"

#     uy = dot(u, cy)

#     # ★ここを現実的に：0.001とかでも割るとメートル級に暴走する
#     # まずは閾値を緩く（例: cos(89deg)=0.017）して弾く
#     if abs(uy) < 0.02:
#         if dbg:
#             dbg.section("hit.yonly")
#             dbg.set(tag+"colId", col.Id.IntegerValue if col else None, 1)
#             dbg.set(tag+"u", vstr(u), 2)
#             dbg.set(tag+"cy", vstr(cy), 2)
#             dbg.set(tag+"uy", fstr(uy), 1)
#             dbg.set(tag+"B_mm", fstr(ft_to_mm(B)), 1)
#             dbg.set(tag+"D_mm", fstr(ft_to_mm(D)), 1)
#         return None, u"uy too small (near parallel to Y face): {:.6f}".format(uy)

#     vu = unit_xy(view.UpDirection)
#     if vu is None:
#         f_cy_pos = 0.5*(fU + fDk)
#         f_cy_neg = 0.5*(fU + fDk)
#     else:
#         if dot(cy, vu) >= 0:
#             f_cy_pos = fU
#             f_cy_neg = fDk
#         else:
#             f_cy_pos = fDk
#             f_cy_neg = fU

#     addUD = (f_cy_pos if uy >= 0 else f_cy_neg)
#     hy = 0.5*D + addUD
#     ty = hy / abs(uy)

#     if dbg:
#         dbg.section("hit.yonly")
#         dbg.set(tag+"colId", col.Id.IntegerValue if col else None, 1)
#         dbg.set(tag+"u", vstr(u), 2)
#         dbg.set(tag+"cy", vstr(cy), 2)
#         dbg.set(tag+"uy", fstr(uy), 1)
#         dbg.set(tag+"D_mm", fstr(ft_to_mm(D)), 1)
#         dbg.set(tag+"fU_mm", fstr(ft_to_mm(fU)), 1)
#         dbg.set(tag+"fDk_mm", fstr(ft_to_mm(fDk)), 1)
#         dbg.set(tag+"addUD_mm", fstr(ft_to_mm(addUD)), 1)
#         dbg.set(tag+"hy_mm", fstr(ft_to_mm(hy)), 1)
#         dbg.set(tag+"ty_mm", fstr(ft_to_mm(ty)), 1)

#     return ty, None

def mm(x_ft):
    return None if x_ft is None else ft_to_mm(x_ft)

def fmt_eq(label, expr, result_ft):
    """ 'iw_L2 = (half - center) * cosA = (150.0 - 20.0) * 0.9962 = 129.5 mm' みたいな1行 """
    r = mm(result_ft)
    if r is None:
        return u"{}: {}".format(label, expr)
    return u"{}: {} = {:.3f} mm".format(label, expr, r)

def fmt_iw_debug_LR(side, ang, halfL_iw, halfR_iw, half_center, tanA, cosA):
    center = half_center * tanA

    # 今のロジックに合わせて “符号で入替”
    if ang < 0:
        # ang<0 のときは R2=(half - center), L2=(half + center) という形にしてるので
        R2_ft = (halfR_iw - center) * cosA
        L2_ft = (halfL_iw + center) * cosA
        exprR = u"(halfR_iw - center) * cosA"
        exprL = u"(halfL_iw + center) * cosA"
    else:
        L2_ft = (halfL_iw - center) * cosA
        R2_ft = (halfR_iw + center) * cosA
        exprL = u"(halfL_iw - center) * cosA"
        exprR = u"(halfR_iw + center) * cosA"

    lines = []
    lines.append(u"[{}] ang={:.3f}deg tanA={:.6f} cosA={:.6f}".format(side, math.degrees(ang), tanA, cosA))
    lines.append(u"[{}] half_center={:.3f}mm center={:.3f}mm".format(side, mm(half_center), mm(center)))
    lines.append(u"[{}] halfL_iw={:.3f}mm halfR_iw={:.3f}mm (fukashi included)".format(side, mm(halfL_iw), mm(halfR_iw)))
    lines.append(fmt_eq(u"[{}] iw_L2".format(side),
                        u"{} = ({:.3f} -/+ {:.3f}) * {:.6f}".format(exprL, mm(halfL_iw), mm(center), cosA),
                        L2_ft))
    lines.append(fmt_eq(u"[{}] iw_R2".format(side),
                        u"{} = ({:.3f} -/+ {:.3f}) * {:.6f}".format(exprR, mm(halfR_iw), mm(center), cosA),
                        R2_ft))
    lines.append(u"[{}] center_offset={:.3f}mm".format(side, mm(center)))

    return u"\n".join(lines), L2_ft, R2_ft, center


# def fmt_iw_debug(side, ang, half_iw, half_center, tanA, cosA):
#     # side: "i" or "j"（表示用）
#     # 戻り: 複数行文字列（warnsに突っ込む用）
#     center = half_center * tanA

#     # 角度符号で左右の式が入れ替わる（あなたの現行ロジック）
#     if ang < 0:
#         R2_ft = (half_iw - center) * cosA
#         L2_ft = (half_iw + center) * cosA
#         exprR = u"(half_iw - center) * cosA"
#         exprL = u"(half_iw + center) * cosA"
#     else:
#         L2_ft = (half_iw - center) * cosA
#         R2_ft = (half_iw + center) * cosA
#         exprL = u"(half_iw - center) * cosA"
#         exprR = u"(half_iw + center) * cosA"

#     lines = []
#     lines.append(u"[{}] ang={:.3f}deg tanA={:.6f} cosA={:.6f}".format(
#         side, math.degrees(ang), tanA, cosA
#     ))
#     lines.append(u"[{}] half_center={:.3f}mm half_iw={:.3f}mm center=half_center*tanA={:.3f}mm".format(
#         side, mm(half_center), mm(half_iw), mm(center)
#     ))
#     # 数値入りの“展開式”を作る
#     lines.append(fmt_eq(u"[{}] iw_L2".format(side),
#                         u"{} = ({:.3f} -/+ {:.3f}) * {:.6f}".format(exprL, mm(half_iw), mm(center), cosA),
#                         L2_ft))
#     lines.append(fmt_eq(u"[{}] iw_R2".format(side),
#                         u"{} = ({:.3f} -/+ {:.3f}) * {:.6f}".format(exprR, mm(half_iw), mm(center), cosA),
#                         R2_ft))
#     lines.append(u"[{}] center_offset={:.3f}mm".format(side, mm(center)))

#     # 警告に欲しいのが “iw_L2/R2 と center_offset” だけならここまででOK
#     return u"\n".join(lines), L2_ft, R2_ft, center




def unjoin_with_columns(doc, fi, cols):
    for c in cols:
        try:
            if JoinGeometryUtils.AreElementsJoined(doc, fi, c):
                JoinGeometryUtils.UnjoinGeometry(doc, fi, c)
        except:
            pass

# ============================================================
# MAIN
# ============================================================
doc = revit.doc
view = doc.ActiveView

sel = revit.get_selection()
if not sel:
    forms.alert(u"梁を選択してから実行してな", exitscript=True)

radius_ft = mm_to_ft(SEARCH_MM)
processed = 0
warns = []

with revit.Transaction(u"TaperBeam Auto Params"):

    idx = 0
    for e in sel:
        fi = e if isinstance(e, FamilyInstance) else None
        if fi is None:
            continue

        idx += 1
        dbg_enabled = DEBUG and (DEBUG_MAX is None or idx <= int(DEBUG_MAX))
        dbg = DebugCtx(dbg_enabled, DEBUG_LEVEL, header="beam id={}".format(fi.Id.IntegerValue))

        try:
            if ONLY_STRUCTURAL_FRAMING:
                try:
                    if (fi.Category is None) or (fi.Category.Id.IntegerValue != int(BuiltInCategory.OST_StructuralFraming)):
                        continue
                except:
                    continue

            # --- LocationCurve endpoints ---
            loc = fi.Location
            if not isinstance(loc, LocationCurve):
                warns.append(u"id={0}: LocationCurveなし".format(fi.Id.IntegerValue))
                continue

            crv = loc.Curve
            p0 = crv.GetEndPoint(0)
            p1 = crv.GetEndPoint(1)

            dbg.section("beam")
            dbg.set("p0", vstr(p0), 1)
            dbg.set("p1", vstr(p1), 1)
            dbg.set("p0xy", vstr(to_xy(p0)), 2)
            dbg.set("p1xy", vstr(to_xy(p1)), 2)

            # --- base_w ---
            base_w, errw = get_base_w(fi)
            dbg.section("params")
            dbg.set("base_w_ft", fstr(base_w), 2)
            dbg.set("base_w_mm", fstr(ft_to_mm(base_w) if base_w else None), 2)

            if errw:
                warns.append(u"id={0}: {1}".format(fi.Id.IntegerValue, errw))
                continue

            # 端点近傍で柱探索
            col_a, _ = nearest_column(doc, p0, radius_ft)
            col_b, _ = nearest_column(doc, p1, radius_ft)

            dbg.section("col.pick")
            dbg.set("col_a", col_a.Id.IntegerValue if col_a else None, 1)
            dbg.set("col_b", col_b.Id.IntegerValue if col_b else None, 1)

            if col_a is None or col_b is None:
                warns.append(u"id={0}: 端点近傍に柱を拾えず".format(fi.Id.IntegerValue))
                continue

            # p0側がi柱かを確定
            p0_xy = to_xy(p0)
            p1_xy = to_xy(p1)
            Ca = col_center_xy(col_a)
            Cb = col_center_xy(col_b)

            dbg.section("col.center")
            dbg.set("Ca", vstr(Ca), 2)
            dbg.set("Cb", vstr(Cb), 2)

            if Ca is None or Cb is None:
                warns.append(u"id={0}: 柱中心取得失敗".format(fi.Id.IntegerValue))
                continue
            Ca = to_xy(Ca)
            Cb = to_xy(Cb)

            d_p0_a = (p0_xy - Ca).GetLength()
            d_p0_b = (p0_xy - Cb).GetLength()

            if d_p0_a <= d_p0_b:
                i_pt, j_pt = p0, p1
                i_col, j_col = col_a, col_b
                Ci, Cj = Ca, Cb
            else:
                i_pt, j_pt = p1, p0
                i_col, j_col = col_b, col_a
                Ci, Cj = Cb, Ca

            dbg.section("ij")
            dbg.set("d_p0_a_ft", fstr(d_p0_a), 2)
            dbg.set("d_p0_b_ft", fstr(d_p0_b), 2)
            dbg.set("d_p0_a_mm", fstr(ft_to_mm(d_p0_a)), 2)
            dbg.set("d_p0_b_mm", fstr(ft_to_mm(d_p0_b)), 2)
            dbg.set("i_pt", vstr(i_pt), 1)
            dbg.set("j_pt", vstr(j_pt), 1)
            dbg.set("i_col", i_col.Id.IntegerValue if i_col else None, 1)
            dbg.set("j_col", j_col.Id.IntegerValue if j_col else None, 1)

            # join解除（必要なら）
            unjoin_with_columns(doc, fi, [i_col, j_col])
            try:
                doc.Regenerate()
            except:
                pass

            # 梁軸
            ex_axis = unit_xy(to_xy(j_pt) - to_xy(i_pt))
            if ex_axis is None:
                warns.append(u"id={0}: 梁方向がゼロ（i_pt==j_pt）".format(fi.Id.IntegerValue))
                continue
            ey_axis = perp_xy(ex_axis)

            dbg.section("axis")
            dbg.set("ex_axis", vstr(ex_axis), 1)
            dbg.set("ey_axis", vstr(ey_axis), 1)

            # 角度（View基準）
            ang_raw = signed_view_angle_rad(ex_axis, view)
            ang = normalize_angle_pm90(ang_raw)
            end_ang = compute_end_angle_signed_from_ang(ang)

            dbg.section("angle")
            dbg.set("ang_raw_deg", fstr(math.degrees(ang_raw)), 1)
            dbg.set("ang_deg", fstr(math.degrees(ang)), 1)
            dbg.set("end_ang_deg", fstr(math.degrees(end_ang)), 1)

            dbg.section("view")
            dbg.set("view.type", str(view.ViewType), 1)
            dbg.set("view.right", vstr(view.RightDirection), 2)
            dbg.set("view.up", vstr(view.UpDirection), 2)

            # trig（以降で使うのでここで確定）
            A = abs(ang)
            cosA = math.cos(A)
            tanA = math.tan(A)

            dbg.section("trig")
            dbg.set("A_deg", fstr(math.degrees(A)), 2)
            dbg.set("cosA", fstr(cosA), 2)
            dbg.set("tanA", fstr(tanA), 2)

            # =========================================================
            # L（柱面〜柱面）：柱中心間 - (中心→面)×2
            # =========================================================
            center_len = (to_xy(Cj) - to_xy(Ci)).GetLength()

            h_i, err_hi = col_hit_face_dist_along_u_Auto(i_col, ex_axis, view, dbg=dbg, tag="i.")
            h_j, err_hj = col_hit_face_dist_along_u_Auto(j_col, ex_axis, view, dbg=dbg, tag="j.")

            dbg.section("hit")
            dbg.set("center_len_mm", fstr(ft_to_mm(center_len)), 1)
            dbg.set("h_i_mm", fstr(ft_to_mm(h_i) if h_i else None), 1)
            dbg.set("h_j_mm", fstr(ft_to_mm(h_j) if h_j else None), 1)
            dbg.set("err_hi", err_hi, 1)
            dbg.set("err_hj", err_hj, 1)

            if err_hi or err_hj or h_i is None or h_j is None:
                warns.append(u"id={0}: Yonly hit fail i={1} j={2}".format(
                    fi.Id.IntegerValue, err_hi or u"?", err_hj or u"?"
                ))
                continue

            plan_face_len = center_len - h_i - h_j

            dbg.section("L")
            dbg.set("plan_face_len_mm", fstr(ft_to_mm(plan_face_len)), 1)

            if plan_face_len <= 1e-9:
                warns.append(u"id={0}: L<=0 (center={1:.1f} hi={2:.1f} hj={3:.1f} mm)".format(
                    fi.Id.IntegerValue,
                    ft_to_mm(center_len), ft_to_mm(h_i), ft_to_mm(h_j)
                ))
                continue
            er = set_double(fi, P_I_COL_OFFSET, h_i)
            if er:
                warns.append(u"id={0}: i_column_offset write {1}".format(fi.Id.IntegerValue, er))



            # 柱サイズ（記録用）
            face_i_auto = column_face_size_from_type(i_col, ey_axis)
            face_j_auto = column_face_size_from_type(j_col, ey_axis)
            if face_i_auto is not None:
                face_i_auto = mm_to_ft(ROUND_COL_MM * round(ft_to_mm(face_i_auto) / ROUND_COL_MM))
            if face_j_auto is not None:
                face_j_auto = mm_to_ft(ROUND_COL_MM * round(ft_to_mm(face_j_auto) / ROUND_COL_MM))

            dbg.section("col.size")
            dbg.set("face_i_auto_mm", fstr(ft_to_mm(face_i_auto) if face_i_auto else None), 2)
            dbg.set("face_j_auto_mm", fstr(ft_to_mm(face_j_auto) if face_j_auto else None), 2)

            # =========================================================
            # i側/j側パラ計算
            # =========================================================
            vals_i = None
            vals_j = None

            # =========================================================
            # ---- i側 ----  (LRフカシ込み + 式展開ログ)
            # =========================================================
            vals_i = None

            B_i, D_i, Bsrc_i, Dsrc_i = get_col_bd(i_col)
            origin_i = fmt_halves_origin("i", i_col, B_i, D_i, Bsrc_i, Dsrc_i)

            half_center_i, halfL_iw_i, halfR_iw_i, err2 = get_halves_center_and_iw_LR_with_fukashi(
                i_col, ey_axis,
                u"フカシ01", u"フカシ02",
                dbg=dbg, tag="i."
            )

            dbg.section("equations")
            dbg.set("i.origin", origin_i, 1)

            if err2:
                warns.append(u"id={0}: i側 halves fail {1}".format(fi.Id.IntegerValue, err2))
                dbg.set("i.err", err2, 1)
            else:
                # 式展開ログ ＋ 実計算（iw_L2/iw_R2/center_offset）
                eq_i, iw_L2, iw_R2, center_i = fmt_iw_debug_LR(
                    "i",
                    ang,
                    halfL_iw_i, halfR_iw_i,
                    half_center_i,
                    tanA, cosA
                )

                dbg.set("i.eq", eq_i, 1)

                # 書き戻し用
                vals_i = {
                    "L2": iw_L2,
                    "R2": iw_R2,
                    "center_offset": center_i,
                }

            # =========================================================
            # ---- j側 ----  (LRフカシ込み + 式展開ログ)
            # =========================================================
            vals_j = None

            B_j, D_j, Bsrc_j, Dsrc_j = get_col_bd(j_col)
            origin_j = fmt_halves_origin("j", j_col, B_j, D_j, Bsrc_j, Dsrc_j)

            half_center_j, halfL_jw_j, halfR_jw_j, err2 = get_halves_center_and_iw_LR_with_fukashi(
                j_col, ey_axis,
                u"フカシ03", u"フカシ04",
                dbg=dbg, tag="j."
            )

            dbg.section("equations")
            dbg.set("j.origin", origin_j, 1)

            if err2:
                warns.append(u"id={0}: j側 halves fail {1}".format(fi.Id.IntegerValue, err2))
                dbg.set("j.err", err2, 1)
            else:
                ang_j = -ang  # ★j側だけ符号反転（±centerの割当を逆にする）

                eq_j, jw_L2, jw_R2, center_j = fmt_iw_debug_LR(
                    "j",
                    ang_j,  # ★ここだけ ang じゃなく ang_j
                    halfL_jw_j, halfR_jw_j,
                    half_center_j,
                    tanA, cosA
                )

                dbg.set("j.eq", eq_j, 1)
                dbg.set("j.ang_used_deg", fstr(math.degrees(ang_j)), 1)

                vals_j = {
                    "L2": jw_L2,
                    "R2": jw_R2,
                    "center_offset": center_j,
                }



            # 延長はゼロ（元コード踏襲）
            try:
                p_s = fi.LookupParameter(u"始端延長")
                p_e = fi.LookupParameter(u"終端延長")
                if p_s and (not p_s.IsReadOnly) and p_s.StorageType == StorageType.Double:
                    p_s.Set(0.0)
                if p_e and (not p_e.IsReadOnly) and p_e.StorageType == StorageType.Double:
                    p_e.Set(0.0)
            except:
                pass

            # --------------------------------------------------------
            # WRITE BACK
            # --------------------------------------------------------
            if not DEBUG_ONLY:
                # L（あなたの独自パラ）
                er = set_double(fi, P_BEAM_LEN, plan_face_len)
                if er:
                    warns.append(u"id={0}: L書込 {1}".format(fi.Id.IntegerValue, er))

                # 柱サイズ（記録）
                if face_i_auto is not None:
                    er = set_double(fi, P_I_COL, face_i_auto)
                    if er: warns.append(u"id={0}: i柱サイズ {1}".format(fi.Id.IntegerValue, er))
                if face_j_auto is not None:
                    er = set_double(fi, P_J_COL, face_j_auto)
                    if er: warns.append(u"id={0}: j柱サイズ {1}".format(fi.Id.IntegerValue, er))

                # angle / End_angle
                er = set_double(fi, P_ANGLE, ang)
                if er: warns.append(u"id={0}: angle write {1}".format(fi.Id.IntegerValue, er))
                er = set_double(fi, P_END_ANGLE, end_ang)
                if er: warns.append(u"id={0}: End_angle write {1}".format(fi.Id.IntegerValue, er))

                # i側
                if vals_i is not None:
                    for pn, v in [
                        (P_IW_R2, vals_i.get("R2")),
                        (P_IW_L2, vals_i.get("L2")),
                        (P_I_CENTER, vals_i.get("center_offset")),
                        (P_I_TAPER, vals_i.get("taper")),
                        (P_I_TAPER_OFF, vals_i.get("taper_offset")),
                    ]:
                        if v is None:
                            continue
                        er = set_double(fi, pn, v)
                        if er: warns.append(u"id={0}: i側書込 {1}".format(fi.Id.IntegerValue, er))

                # j側
                if vals_j is not None:
                    for pn, v in [
                        (P_JW_R2, vals_j.get("R2")),
                        (P_JW_L2, vals_j.get("L2")),
                        (P_J_CENTER, vals_j.get("center_offset")),
                        (P_J_TAPER, vals_j.get("taper")),
                        (P_J_TAPER_OFF, vals_j.get("taper_offset")),
                    ]:
                        if v is None:
                            continue
                        er = set_double(fi, pn, v)
                        if er: warns.append(u"id={0}: j側書込 {1}".format(fi.Id.IntegerValue, er))

                try:
                    doc.Regenerate()
                except:
                    pass

            processed += 1

        except Exception as ex:
            # 例外もログに残す
            dbg.exc(ex, where="main loop")
            raise
        finally:
            # continueでも必ずログを吐く
            dbg.dump(log)

# ============================================================
# SUMMARY
# ============================================================
msg = u"処理: {0} 件\n".format(processed)
if warns:
    msg += u"\n警告/スキップ:\n" + u"\n".join(warns[:120])
    if len(warns) > 120:
        msg += u"\n...(他 {0} 件)".format(len(warns) - 120)

forms.alert(msg, title=u"完了")
