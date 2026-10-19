import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT
sys.path.insert(0, str(APP))

from config import Config  # noqa: E402

uri = Config.SQLALCHEMY_DATABASE_URI or ""
masked = uri[:28] + "..." if len(uri) > 28 else uri
print("build: DATABASE_URL ->", masked)
print("build: dialect ->", ("postgres" if "postgres" in uri else "sqlite"))

import py_compile  # noqa: E402

targets = ["app.py", "config.py", "extensions.py", "models.py", "seed.py",
           "simulation.py", "utils.py", "routes/auth.py", "routes/student.py",
           "routes/simulator.py", "routes/admin.py"]
for t in targets:
    py_compile.compile(str(APP / t), doraise=True)
    print("build: compile OK", t)

import importlib.util  # noqa: E402

for pkg in ("flask", "flask_sqlalchemy", "flask_login", "dotenv", "psycopg2"):
    assert importlib.util.find_spec(pkg), f"missing dependency: {pkg}"
    print("build: dep OK", pkg)

# Conectividade: tenta Postgres (Neon), cai para SQLite se indisponivel.
from sqlalchemy import create_engine, text  # noqa: E402

eng = create_engine(Config.SQLALCHEMY_DATABASE_URI)
try:
    with eng.connect() as c:
        ver = c.execute(text("SELECT version()")).scalar() if "postgres" in uri else "sqlite-local"
        print("build: connect OK ->", str(ver)[:80])
except Exception as e:  # noqa: BLE001
    print("build: connect FAIL ->", str(e)[:200])
    sys.exit(1)
print("build: PASS")
