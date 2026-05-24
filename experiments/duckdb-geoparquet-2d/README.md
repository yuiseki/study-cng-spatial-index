# DuckDB + GeoParquet 2D Spatial Index Experiment

## 結論（先読み）

1. **bbox-cols（xmin/ymin/xmax/ymax 列）が最速・最正確。**
   viewport サイズに関わらず 2–5 ms で一定。DuckDB の row group column statistics が自動的に pruning を行うため、IN 述語 overhead がない。

2. **IN 述語 overhead がすべての cell-based scheme に共通するボトルネック。**
   セル数が ~500 を超えると DuckDB は顕著に遅くなる。これは 3D Morton で観測された同じ問題の 2D 版。

3. **各 scheme のスイートスポット:**
   - H3: res=8–9（小〜中 viewport、2–6 ms、10–261 cells）
   - GeoHash: prec=6–7（2–10 ms；prec=8 以上は IN が爆発し 538 ms）
   - Quadkey: z=15–17（2–11 ms；z=19 の大 viewport は 92 ms）
   - Morton2D: viewport が大きくなっても range 数の増加が緩やか（最大 252 ranges、10 ms）

4. **コースすぎる解像度は FP が激増する。**
   H3 res=7・GeoHash prec=5・Quadkey z=15 は vp=0.01° で全件の 30–60% を返してしまう。

---

## 目的

PostGIS GiST を持たない DuckDB + Parquet 環境で、
代表的な 2D 空間インデックス設計を比較する。

[3D Route 実験](../duckdb-geoparquet-3d-route/README.md) が「高さ次元を持つ 3D key design」を比較したのに対し、
本実験は **2D（水平位置のみ）** の空間インデックスパターンを比較する。

## 実験設定

| 項目 | 値 |
|------|-----|
| データ（点） | OSM 台東区 点フィーチャー 25,821 件 |
| データ（面） | OSM 台東区 建物 36,521 件（bbox cover） |
| 中心座標 | lon=139.785, lat=35.713 |
| viewport サイズ | 0.01° / 0.05° / 0.10° |
| radius | 500 m / 1,000 m / 2,000 m |
| DuckDB | 1.3.x |
| Parquet row group | 50,000 rows |

## 比較する scheme

| scheme | key | sort key | 特徴 |
|--------|-----|----------|------|
| H3 | 六角形セル文字列 | (resolution, h3_cell) | 均等面積セル、res=7–10 |
| GeoHash | Base32 文字列 | (precision, geohash) | 文字列プレフィックス局所性 |
| Quadkey | Web Mercator タイル文字列 | (zoom, quadkey) | Web 地図タイルと完全互換 |
| Morton2D | uint64 Z-order key | (zoom, key_u64) | single sorted key、box query で OR ranges |
| bbox-cols | xmin/ymin/xmax/ymax 列 | (xmin) | DuckDB column statistics で自動 pruning |

## Parquet ファイルサイズ

| ファイル | 行数 | サイズ |
|----------|------|--------|
| cells_h3_points.parquet (res=7–10) | 103,284 | 0.44 MB |
| cells_geohash_points.parquet (prec=5–8) | 103,284 | 0.50 MB |
| cells_quadkey_points.parquet (z=15,17,19) | 77,463 | 0.39 MB |
| cells_morton2d_points.parquet (z=19) | 25,821 | 0.19 MB |
| cells_h3_poly.parquet (res=7–10) | 146,090 | 0.72 MB |
| cells_geohash_poly.parquet (prec=5–8) | 197,702 | 1.02 MB |
| cells_quadkey_poly.parquet (z=15,17,19) | 128,096 | 0.63 MB |
| cells_morton2d_poly.parquet (z=19) | 50,937 | 0.27 MB |
| points_with_bbox.geoparquet | 25,821 | 1.57 MB |
| poly_with_bbox.geoparquet | 36,521 | 3.86 MB |

## viewport_points 結果（点クエリ）

### vp=0.01°（約 1 km 四方）

| scheme | resolution | n_cells / n_ranges | count | avg_ms |
|--------|-----------|---------------------|-------|--------|
| **bbox_cols** | — | — | **3,400** | **2.2** |
| Morton2D | z=19 | 8 ranges | 3,874 | 2.0 |
| H3 | res=9 | 10 cells | 3,022 | 2.1 |
| H3 | res=10 | 71 cells | 3,349 | 2.6 |
| GeoHash | prec=7 | 72 cells | 4,344 | 2.7 |
| Quadkey | z=17 | 24 cells | 4,641 | 2.4 |
| Quadkey | z=19 | 285 cells | 3,614 | 3.6 |
| GeoHash | prec=6 | 3 cells | 5,472 | 2.1 |
| H3 | res=8 | 2 cells | 3,493 | 2.2 |

### vp=0.05°（約 5 km 四方）

| scheme | resolution | n_cells / n_ranges | count | avg_ms |
|--------|-----------|---------------------|-------|--------|
| **bbox_cols** | — | — | **25,821** | **4.1** |
| Quadkey | z=15 | 35 cells | 25,821 | 5.2 |
| GeoHash | prec=6 | 50 cells | 25,821 | 5.3 |
| H3 | res=8 | 38 cells | 25,821 | 5.3 |
| Morton2D | z=19 | 104 ranges | 25,821 | 7.2 |
| H3 | res=9 | 261 cells | 25,819 | 6.3 |
| Quadkey | z=17 | 456 cells | 25,821 | 6.5 |
| GeoHash | prec=7 | 1,369 cells | 25,821 | 9.7 |
| H3 | res=10 | 1,814 cells | 25,821 | 10.9 |

### vp=0.10°（約 10 km 四方）

| scheme | resolution | n_cells / n_ranges | count | avg_ms |
|--------|-----------|---------------------|-------|--------|
| **bbox_cols** | — | — | **25,821** | **3.9** |
| H3 | res=8 | 148 cells | 25,821 | 5.9 |
| GeoHash | prec=6 | 209 cells | 25,821 | 5.9 |
| Morton2D | z=19 | 252 ranges | 25,821 | 9.6 |
| Quadkey | z=15 | 132 cells | 25,821 | 5.6 |
| H3 | res=9 | 1,032 cells | 25,821 | 8.6 |
| Quadkey | z=17 | 1,748 cells | 25,821 | 11.2 |
| GeoHash | prec=7 | 5,402 cells | 25,821 | 20.9 |
| H3 | res=10 | 7,253 cells | 25,821 | 28.3 |
| Quadkey | z=19 | 26,460 cells | 25,821 | **92.3** |
| GeoHash | prec=8 | 170,236 cells | 25,821 | **538.7** |

## viewport_poly 結果（建物クエリ）

| scheme | resolution | vp=0.01° count | vp=0.01° ms | vp=0.05° ms | vp=0.10° ms |
|--------|-----------|---------------|-------------|-------------|-------------|
| **bbox_cols** | — | **4,833** | **3.0** | **5.6** | **5.1** |
| Morton2D | z=19 | 5,518 | 2.5 | 9.9 | 12.7 |
| H3 | res=9 | 4,249 | 2.5 | 7.8 | 9.9 |
| H3 | res=10 | 4,709 | 3.1 | 14.6 | 32.1 |
| GeoHash | prec=7 | 6,042 | 3.2 | 10.9 | 22.3 |
| GeoHash | prec=6 | 7,834 | 2.7 | 7.5 | 7.4 |
| Quadkey | z=17 | 6,462 | 3.1 | 9.5 | 13.7 |
| Quadkey | z=19 | 5,216 | 3.8 | 29.6 | **96.1** |
| GeoHash | prec=8 | 4,999 | 8.0 | 130.3 | **514.7** |

## radius_points 結果（H3 grid_disk）

| resolution | r=500m (k, cells) | count | ms | r=1000m (k, cells) | count | ms |
|-----------|-------------------|-------|----|--------------------|-------|-----|
| res=9 | k=3, 37 cells | 11,117 | 3.6 | k=6, 127 cells | 24,858 | 5.9 |
| res=10 | k=8, 217 cells | 9,224 | 3.9 | k=16, 817 cells | 24,616 | 7.8 |

H3 radius は grid_disk による近似のため、真の円より大きいエリアをカバーする。
正確な距離フィルタには bbox_cols + 事後 Haversine フィルタが適している。

## IN 述語 overhead の閾値

DuckDB における IN 述語のスケーリング（点クエリ vp=0.10°):

| cells / ranges | avg_ms |
|----------------|--------|
| ~100–200 | 5–10 ms |
| ~500–1,000 | 8–12 ms |
| ~5,000–7,000 | 20–28 ms |
| ~26,000 | 92 ms |
| ~170,000 | 539 ms |

**IN 述語は ~500 cells を超えると線形的にコストが増加する。**
bbox-cols と Morton2D（BETWEEN ranges）はこの overhead から自由。

## 制約

- 点クエリの「実際の件数」は bbox_cols の値を基準とした（PostGIS PIP なし）
- polygon cover は bbox ベース（strict polygon cover ではない）
- H3 poly は `geo_to_cells`（inner containment）の fallback として centroid cell を使用
- radius は H3 `grid_disk` による近似（真の円ではない）
- Parquet は local filesystem（object storage での range request 効率は未計測）
