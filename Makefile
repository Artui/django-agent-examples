.DEFAULT_GOAL := help
.PHONY: help init backend react test build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

init: ## Install everything and seed the demo database
	cd backend && uv sync
	cd backend && uv run python manage.py migrate
	cd backend && uv run python manage.py seed_board
	cd react && pnpm install
	cd vue && pnpm install
	cd svelte && pnpm install
	cd angular && pnpm install

backend: ## Run the shared backend and the admin surface on :8000 (ASGI, required)
	cd backend && uv run uvicorn demo.asgi:application --port 8000 --reload

react: ## Run the React app on :5173
	cd react && pnpm dev

vue: ## Run the Vue app on :5174
	cd vue && pnpm dev

svelte: ## Run the Svelte app on :5175
	cd svelte && pnpm dev

angular: ## Run the Angular app on :4200
	cd angular && pnpm dev

test: ## Drive the backend and both agent endpoints
	cd backend && uv run python -m pytest

build: ## Type-check and build every app
	cd react && pnpm build
	cd vue && pnpm build
	cd svelte && pnpm build
	cd angular && pnpm build

clean: ## Remove the demo database and build output
	rm -f backend/db.sqlite3
	rm -rf react/dist vue/dist svelte/dist angular/dist angular/.angular
