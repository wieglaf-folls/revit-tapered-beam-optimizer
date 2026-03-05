# revit-tapered-beam-optimizer

> 🚧 **Under Development** — Tapered Beam Geometry Auto-Optimization Tool

---

## Overview

An automation tool that handles the complex geometric calculations required for tapered structural beams, ensuring seamless alignment and parameter synchronization in Revit.

（構造設計において複雑な計算を要するテーパー梁の形状処理を自動化し、Revit上での正確な配置とパラメータ同期を実現するツール）

---

## Challenges & Solutions

| | 日本語 | English |
|---|---|---|
| **課題 / Challenges** | 断面変化（テーパー）を伴う梁の配置計算が複雑 | High complexity in calculating cross-sectional changes and alignments. |
| | 梁の両端でレベルや幅が違うと整合性が崩れやすい | Prone to coordination errors when beam ends have different elevations or widths. |
| | 手動でのパラメータ入力による入力ミスの多発 | Frequent manual input errors in complex structural parameters. |
| **解決策 / Solution** | Revit APIを用いたベクトル演算による自動形状生成 | Implemented vector-based geometric logic via Revit API for automatic generation. |
| | 両端の断面情報を参照し、動的にパラメータを計算 | Dynamically calculates parameters based on cross-sectional data at both ends. |
| **成果 / Results** | 複雑なテーパー梁のモデリング時間を大幅に短縮 | Significant reduction in modeling time for complex tapered elements. |
| | 幾何学的な整合性を100%保証し、設計ミスを根絶 | Ensures 100% geometric consistency, eliminating critical design errors. |

---

## Demo

🎬 **Coming Soon** (Under final adjustments)

---

## Technical Solution

### Automated Face Detection Logic

Uses vector dot products to compare the beam's direction with the column's local coordinate system (BasisX/BasisY), automatically identifying the correct reference face for hit distance calculations.

（梁のベクトルと柱のローカル座標系の内積を比較し、計算基準となる柱の面を自動で特定するロジックを実装）

```python
# 梁方向(u)に対して、柱のX面かY面どちらが適切かを内積で判定
use_axis = "X" if abs(ux) >= abs(uy) else "Y"
n = cx if use_axis == "X" else cy
un = ux if use_axis == "X" else uy
```

### Dynamic Geometric Computation

Calculates precise offset values (`center_offset`, `iw_L2`, `iw_R2`) by factoring in beam skew angles and column "Fukashi" (added finish thickness) using trigonometric functions.

（梁の斜め角や柱の「フカシ」寸法を考慮し、三角関数を用いて `center_offset` や `iw_L2/R2` などの精密なオフセット値を動的に算出）

```python
# 梁の斜め角(A)から三角関数(tan/cos)を用いて、柱面での正確な幅(L2/R2)を算出
center = half_center * tanA
if ang < 0:
    R2_ft = (halfR_iw - center) * cosA
    L2_ft = (halfL_iw + center) * cosA
else:
    L2_ft = (halfL_iw - center) * cosA
    R2_ft = (halfR_iw + center) * cosA
```

### Robust Error Handling & Logging

Integrated a custom `DebugCtx` class to provide detailed execution logs for each beam, ensuring transparency in complex geometric overrides.

（独自の `DebugCtx` クラスを実装し、梁一本ごとの計算過程を詳細にログ出力。複雑な幾何形状のオーバーライドにおける透明性を確保）

---

## How to Use

### Prerequisites

- **Autodesk Revit 2024** (or later)
- **pyRevit** installed — [Download here](https://github.com/pyrevitlabs/pyRevit/releases)

### Setup

**1. Clone or Download this Repository**
```
git clone https://github.com/wieglaf-folls/revit-tapered-beam-optimizer.git
```

**2. Load the Custom Family**
1. Open your Revit project
2. Go to **Insert** tab → **Load Family**
3. Navigate to the `families/` folder and select the `.rfa` file
4. Click **Open**

> ⚠️ The script will not work correctly without the custom family loaded.

**3. Run the Script via pyRevit**
1. Go to the **pyRevit** tab in the Revit ribbon
2. Click **pyRevit** → **Tools** → **Run Script**
3. Navigate to the `src/` folder and select the script
4. Click **Open** to execute

---

## Future Scope

The current version focuses on high-precision horizontal tapered beams with X-axis angular adjustments. The next milestone is to **expand the logic to support Y-axis (vertical) angular alignment**, enabling full 3D geometric optimization for even more complex structural framing.

（現在はX軸方向の角度付き水平テーパー梁に特化していますが、今後は **Y軸方向（垂直方向）の角度対応** へとロジックを拡張し、より複雑な構造フレームに対してもフル3Dでの幾何形状最適化を可能にする予定です。）

---

## License

MIT License — see [LICENSE](LICENSE) for details.
