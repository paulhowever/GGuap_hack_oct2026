GODOT ?= /Applications/Godot.app/Contents/MacOS/Godot
GODOT_PROJECT ?= godot
WEB_DIR ?= $(CURDIR)/web

.PHONY: setup vendor export-web assemble backend dev demo test test-web fixtures

setup:
	cd backend && uv sync
	cd pipeline && uv sync
	cd web && npm install
	$(MAKE) vendor

vendor:
	cd web && npm run vendor

export-web:
	mkdir -p dist/web
	"$(GODOT)" --headless --path "$(GODOT_PROJECT)" --export-release "Web" "$(CURDIR)/dist/web/index.html"

assemble:
	mkdir -p dist/web
	rsync -a --exclude node_modules --exclude test --exclude package.json --exclude package-lock.json web/ dist/web/
	printf '{"git_sha": "%s%s", "built_at": "%s"}\n' "$$(git rev-parse HEAD)" "$$(git diff --quiet HEAD -- web godot || echo -dirty)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > dist/web/version.json

backend:
	cd backend && KARAOKE_WEB_DIR="$(WEB_DIR)" KARAOKE_GIT_SHA=$$(git rev-parse HEAD) uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

dev: export-web assemble
	$(MAKE) backend WEB_DIR=$(CURDIR)/dist/web

demo: assemble
	$(MAKE) backend WEB_DIR=$(CURDIR)/dist/web

test:
	cd backend && uv run pytest
	cd pipeline && uv run pytest
	cd web && npm test

test-web:
	cd web && npm test

fixtures:
	rsync -a contracts/fixtures/ "$(GODOT_PROJECT)/mock/"
	rsync -a contracts/fixtures/ web/mock/
