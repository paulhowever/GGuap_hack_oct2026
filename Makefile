GODOT ?= /Applications/Godot.app/Contents/MacOS/Godot

.PHONY: setup vendor export-web assemble backend dev test test-web fixtures

setup:
	cd backend && uv sync
	cd web && npm install
	$(MAKE) vendor

vendor:
	cd web && npm run vendor

export-web:
	mkdir -p dist/web
	"$(GODOT)" --headless --path godot --export-release "Web" ../dist/web/index.html

assemble:
	mkdir -p dist/web
	rsync -a --exclude node_modules --exclude test --exclude package.json --exclude package-lock.json web/ dist/web/
	printf '{"git_sha": "%s%s", "built_at": "%s"}\n' "$$(git rev-parse HEAD)" "$$(git diff --quiet HEAD -- web godot || echo -dirty)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > dist/web/version.json

backend:
	cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

dev: export-web assemble backend

test:
	cd backend && uv run pytest

test-web:
	cd web && npm test

fixtures:
	rsync -a contracts/fixtures/ godot/mock/
	rsync -a contracts/fixtures/ web/mock/
