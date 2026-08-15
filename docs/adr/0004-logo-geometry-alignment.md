# ADR 0004：景枢 Logo 几何对齐与资产统一

- 状态：已接受
- 日期：2026-08-15
- 影响范围：品牌资产、Console、favicon、应用图标、发布文档

## 背景

早期 Logo 变体分别内嵌了近似但不完全一致的曲面路径。两侧曲面带的几何中心和中部间距存在轻微偏差，导致小尺寸应用图标中出现不对称、中心星视觉偏移和左右曲面贴近的问题。继续在单个文件上手工修正会使标准标志、字标、favicon 和前端副本再次漂移。

## 决策

以 `docs/brand/assets/scenara-mark.svg` 的 `64 x 64` 视图框建立唯一几何基线：

```text
垂直中轴：x = 32
中心四向星：几何中心 (32, 32)
上方/左侧曲面：原始母路径 translate(0 -3)
下方/右侧曲面：原始母路径 rotate(180 32 32) 后 translate(0 3)
```

本次调整只改变曲面带相对位置和中心星/镂空的几何对齐，不改变品牌颜色、渐变、视图框、文字内容、应用图标背景或 Logo 的整体造型。

以下资产必须使用同一几何母体：

```text
docs/brand/assets/scenara-mark.svg
docs/brand/assets/scenara-mark-inverse.svg
docs/brand/assets/scenara-mark-mono.svg
docs/brand/assets/scenara-app-icon.svg
docs/brand/assets/scenara-wordmark-horizontal-en.svg
docs/brand/assets/scenara-wordmark-horizontal-zh.svg
docs/brand/assets/scenara-wordmark-vertical.svg
frontend/console/src/assets/scenara-mark.svg
frontend/console/public/favicon.svg
```

## 验证与约束

- 每个 SVG 必须能够被 XML 解析。
- 每个变体必须包含一处 `translate(0 -3)` 和一处 `translate(0 3) rotate(180 32 32)`；单色版路径不带渐变 fill。
- 中心星路径不得包含额外平移。
- 前端生产构建必须通过。
- 品牌资产变更必须同步更新 `更新日志.md`、`docs/brand/BRAND.md` 和 `docs/brand/assets/README.md`。

使用场景不得再次旋转、拉伸、重排渐变或修改曲面带间距。若未来需要新构型，必须新建 ADR，不得覆盖当前几何基线。
