.PHONY: setup lockdown start stop preflight demo test

setup:
	bash scripts/00_install_gvisor.sh
	bash scripts/02_stage_models.sh

lockdown:
	bash scripts/01_lockdown_egress.sh

start:
	bash scripts/03_start_services.sh

stop:
	bash scripts/04_stop_services.sh

preflight:
	python3 scripts/preflight.py

demo: preflight
	bash scripts/03_start_services.sh
	command -v open >/dev/null 2>&1 && open http://127.0.0.1:8501 \
		|| command -v xdg-open >/dev/null 2>&1 && xdg-open http://127.0.0.1:8501 \
		|| echo "open http://127.0.0.1:8501 in a browser"

test:
	pytest tests/ -v
