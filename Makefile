.PHONY: install lint test build dev-dashboard

# Backend commands
install-backend:
	cd backend && python -m pip install --upgrade pip && pip install -r requirements.txt && pip install ruff

lint-backend:
	cd backend && ruff check .

test-backend:
	cd backend && python -m tests.test_oneway

compile-backend:
	cd backend && python -m compileall -q .

# Dashboard commands
install-dashboard:
	cd dashboard && npm install

dev-dashboard:
	cd dashboard && npm run dev

build-dashboard:
	cd dashboard && npm run build

# Global commands
install: install-backend install-dashboard
lint: lint-backend
test: test-backend
build: compile-backend build-dashboard
