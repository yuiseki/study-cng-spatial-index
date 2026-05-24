.PHONY: install prepare bench-corridor bench-route summarize all clean

install:
	uv sync

prepare:
	uv run python scripts/prepare_osm_buildings.py
	uv run python scripts/build_obstacles_geoparquet.py
	uv run python scripts/build_occupancy_cells.py

prepare-cells:
	uv run python scripts/build_occupancy_cells.py

bench-corridor:
	uv run python scripts/run_corridor_bench.py

bench-route:
	uv run python scripts/run_route_bench.py

summarize:
	uv run python scripts/summarize_results.py

all: prepare bench-corridor summarize

# Run with a specific row group size
bench-rg:
	uv run python scripts/build_occupancy_cells.py --row-group-size $(RG_SIZE)
	uv run python scripts/run_corridor_bench.py

clean:
	rm -rf data/raw/*.geojson data/prepared/*.parquet data/parquet/*.parquet data/results/
