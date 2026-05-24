# DuckDB + GeoParquet 2D Spatial Index Experiment

## 目的

PostGIS GiST を持たない DuckDB + Parquet 環境で、
代表的な 2D 空間インデックス設計を比較する。

[3D Route 実験](../duckdb-geoparquet-3d-route/README.md) が「高さ次元を持つ 3D key design」を比較したのに対し、
本実験は **2D（水平位置のみ）** の空間インデックスパターンを比較する。

## 比較する scheme

| scheme | key type | sort key | 特徴 |
|--------|----------|----------|------|
| H3 | 六角形セル文字列 | (resolution, h3_cell) | 均等面積セル、Python h3-py v4 |
| GeoHash | Base32 文字列 | (precision, geohash) | 文字列プレフィックス検索可能 |
| Quadkey | Web Mercator タイル文字列 | (zoom, quadkey) | mercantile、Web地図と互換 |
| Morton2D | uint64 Z-order key | (zoom, key_u64) | single sortable key, OR ranges |
| bbox-cols | xmin/ymin/xmax/ymax columns | (xmin) | DuckDB row group pruning + col stats |

## データ

| データ | 件数 |
|--------|------|
| OSM 台東区 点フィーチャー | ~25,000 件 |
| OSM 台東区 建物 (polygon, bbox cover) | 36,521 件 |

## クエリ種別

| 種別 | 対象 | 説明 |
|------|------|------|
| viewport_points | 点 | 矩形 viewport 内の点を返す |
| radius_points | 点 | 中心点から半径 r 内の点（H3 grid_disk による近似） |
| viewport_poly | 面 | 矩形 viewport に重なる建物を返す |

viewport サイズ: 0.01° / 0.05° / 0.1°（約 1 km / 5 km / 10 km 四方）
radius: 500 m / 1,000 m / 2,000 m

## 期待する観察

- **bbox-cols が最もシンプルかつ高速**: DuckDB は xmin/xmax/ymin/ymax の row group statistics を自動利用できる
- **H3 は高解像度 (res=9-10) が viewport に適合**: セル数が多くなりすぎず候補が絞れる
- **GeoHash は文字列 IN 検索が DuckDB で高速**: sorted parquet + prefix locality が効く
- **Quadkey は Web Mercator と完全互換**: tile pyramid との親和性が高い
- **Morton2D は box query で range 分割が多くなる**: 2D 版でも OR overhead が支配的になる可能性がある（3D の教訓）

## 実行方法

```bash
# 2D 用データ準備（PostgreSQL が localhost:55442 で動いている必要あり）
make prepare-2d

# 2D ベンチマーク
make bench-2d
```

## 結果

`data/results/<timestamp>/2d/summary.md` を参照。
（ベンチマーク実行後に生成されます）
