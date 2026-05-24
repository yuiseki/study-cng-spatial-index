# DuckDB + GeoParquet 3D Route Experiment

## 目的

PostGIS GiST を持たない CNG / edge / file-based index 環境で、
3D occupancy grid lookup をする場合に、
どの key design が最も少ないファイルスキャン・少ない候補数・小さいファイルサイズで済むかを DuckDB + Parquet で測る。

## 比較する key design

| scheme | key | 水平解像度 | 垂直解像度 |
|--------|-----|-----------|-----------|
| zfxy | {z}/{f}/{x}/{y} | z に束縛 | z に束縛（64m/unit @ z=19） |
| zxy_heightbin | {xy_z}/{x}/{y}/{vbin}/{hbin} | xy_z に束縛 | vertical_bin_m で独立指定 |
| Morton3D | key_u64 = interleave(local_x, local_y, hbin) | xy_z に束縛 | vbin で独立指定 |

## 実験設定

| 項目 | 値 |
|------|-----|
| データ | OSM 台東区建物 36,521件 |
| 高さモデル | height > levels×3 > default_15m |
| corridor | lon=139.785, lat 35.695→35.731, 幅 100 m |
| altitudes | 30 / 60 / 90 / 120 m |
| clearance | ±5 m |
| DuckDB | 1.3.x |
| Parquet row group | 50,000 rows |

## Parquet ファイルサイズ

| scheme | rows | row groups | size |
|--------|------|------------|------|
| occupancy_zfxy.parquet (z=19-22) | 721,602 | 180 | 5.05 MB |
| occupancy_zxy_heightbin.parquet (vbin=4,8,16m) | 359,905 | 96 | 2.01 MB |
| occupancy_morton3d.parquet (vbin=4,8,16m) | 359,905 | 112 | 1.54 MB |

zfxy は z=19-22 の 4 zoom level を持つため行数・ファイルサイズが大きい。
zxy_heightbin / Morton3D は xy_z=19 固定 + 3 vbin のみ。

## Stage 1: Corridor lookup 結果

### 候補建物数（corridor + altitude band）

| scheme | resolution | alt=30m | alt=60m | alt=90m | alt=120m |
|--------|-----------|---------|---------|---------|----------|
| **actual**| — | **16** | **1** | **0** | **0** |
| zfxy | z=19 | 3,183 | 3,183 | **1** | **1** |
| zfxy | z=20 | 2,205 | 5 | **1** | 0 |
| zfxy | z=21 | 51 | **1** | 0 | 0 |
| zfxy | z=22 | 26 | **1** | 0 | 0 |
| zxy_hbin | vbin=4m | **34** | **1** | 0 | 0 |
| zxy_hbin | vbin=8m | **34** | **1** | 0 | 0 |
| zxy_hbin | vbin=16m | 67 | **1** | 0 | 0 |
| Morton3D | vbin=4m | 41 | **1** | 0 | 0 |
| Morton3D | vbin=8m | 38 | **1** | 0 | 0 |
| Morton3D | vbin=16m | 78 | **1** | 0 | 0 |

### クエリ実行時間（DuckDB, warm Parquet read）

| scheme | resolution | avg (ms) |
|--------|-----------|----------|
| zfxy | z=22 | ~2 ms |
| zxy_heightbin | vbin=4m | ~2 ms |
| **Morton3D** | vbin=4m | **~15 ms** (85–136 ranges) |

**Morton3D は range 分割数が多く（85–136 ranges/query）、DuckDB OR predicate の overhead が支配的になり 5–7× 遅い。**

### zfxy の水平・垂直解像度連動問題

| z | m/f-unit | cands@30m | cands@60m |
|---|----------|-----------|-----------|
| 19 | 64 m | **3,183** (f=0 で全件) | 3,183 |
| 20 | 32 m | 2,205 | 5 |
| 21 | 16 m | 51 | 1 |
| 22 | 8 m | 26 | 1 |

zfxy z=19 では alt=30m の候補が 3,183 件（実際 16 件）。
f の粒度を上げるには z を上げるしかないが、x/y も一緒に細かくなる（z=22 で 1 タイル≈40 m）。

zxy_heightbin vbin=4m は z=19 固定のまま 34 件の候補。これは独立した垂直解像度の利点。

## Stage 2: A* Route search 結果

| scheme | alt=30m | alt=60m | alt=90m | alt=120m |
|--------|---------|---------|---------|----------|
| zfxy z=19 | ✗ | ✗ | ✓ (len=68) | ✓ (len=68) |
| zfxy z=20 | ✗ | ✓ (len=134) | ✓ (len=132) | ✓ (len=130) |
| zfxy z=21 | ✗ | ✓ (len=259) | ✓ (len=259) | ✓ (len=259) |
| zfxy z=22 | ✓ (len=522) | ✓ (len=518) | ✓ (len=518) | ✓ (len=518) |
| zxy_hbin vbin=4m | ✗ | ✓ (len=68) | ✓ (len=66) | ✓ (len=66) |

alt=30m: どの scheme も corridor が建物で完全閉塞（実 16 棟 @ 25–35 m）。
alt=60m: zfxy z=19 は f=0 のまま全建物を blocked と誤判定 → 経路なし。zfxy z=20+ は正しく経路発見。

**lookup_ms は全 scheme で 8–13 ms（Parquet cold read の支配）。route_ms は 0.1–4 ms（A* 自体は軽い）。**

## 結論

1. **zxy_heightbin (vbin=4m) が最もバランスよい。**
   - ファイルサイズ最小（2.01 MB）
   - 候補数最小（alt=30m で 34 件）
   - クエリ時間 ~2 ms
   - 水平・垂直解像度を独立調整できる

2. **zfxy は z=21–22 で comparable になるが、ファイルが大きく用途が限られる。**
   - z=19 は垂直粒度が粗すぎ（64 m/f-unit）
   - z=22 は良好だが 4 zoom level 分を持つとファイルが 5 MB になる

3. **Morton3D は box query には不向き。**
   - single sorted key としての設計は理論上正しいが、
     box query が 85–136 の Morton range に分解され、DuckDB の OR overhead が支配的
   - Point lookup や range クエリが単調な場合（例: 1D histogram lookup）に向く設計

4. **PostGIS GiST との比較（参考）**
   - PostGIS GiST + height range: ~1 ms（同等データ）
   - DuckDB + sorted Parquet: ~2 ms（GiST に近い）
   - DuckDB の row group pruning は、sorted key と適切な row group size があれば GiST に匹敵するスキャン効率を発揮できる

## 制約

- corridor は bbox 矩形近似（swept-circle / true offset polygon ではない）
- occupancy cells は bbox footprint cover（strict polygon cover ではない）
- A* は 2D grid（高度固定、障害物は水平方向のみ）
- Morton3D の interval decomposition は naive な gap_factor merging のみ
- Parquet は local filesystem（object storage での range request 効率は未計測）
