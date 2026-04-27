pipeline {
  agent any

  options {
    skipDefaultCheckout(true)
  }

  environment {
    DOCKER_HOST = "unix:///var/run/docker.sock"
    COMPOSE_FILE = "/workspace/docker-compose.yml"
    COMPOSE_PROJECT_NAME = "queryfile"
    COMPOSE_SERVICES = "milvus etcd minio attu backend frontend"
  }

  stages {
    stage('Up') {
      steps {
        sh '''
          set -e
          if docker compose version >/dev/null 2>&1; then
            COMPOSE="docker compose"
          else
            COMPOSE="docker-compose"
          fi
          $COMPOSE -f "$COMPOSE_FILE" up -d --build $COMPOSE_SERVICES
        '''
      }
    }

    stage('Wait for Backend') {
      steps {
        sh '''
          set -e
          if docker compose version >/dev/null 2>&1; then
            COMPOSE="docker compose"
          else
            COMPOSE="docker-compose"
          fi

          for i in $(seq 1 30); do
            $COMPOSE -f "$COMPOSE_FILE" exec -T backend python - <<'PY' && exit 0
import json, sys, urllib.request
try:
    with urllib.request.urlopen("http://localhost:8000/health", timeout=2) as r:
        data = json.load(r)
    ok = data.get("status") == "ok"
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PY
            sleep 3
          done

          echo "Backend health check failed" >&2
          exit 1
        '''
      }
    }

    stage('Sync') {
      steps {
        sh '''
          set -e
          if docker compose version >/dev/null 2>&1; then
            COMPOSE="docker compose"
          else
            COMPOSE="docker-compose"
          fi
          $COMPOSE -f "$COMPOSE_FILE" exec -T backend python -m backend.app.sync.sync
        '''
      }
    }

    stage('Test') {
      steps {
        sh '''
          set -e
          if docker compose version >/dev/null 2>&1; then
            COMPOSE="docker compose"
          else
            COMPOSE="docker-compose"
          fi

          $COMPOSE -f "$COMPOSE_FILE" exec -T backend python - <<'PY'
import json, sys, urllib.request

payload = {"question": "What is the Synced Brain and how does it sync files?", "top_k": 3, "debug": True}
req = urllib.request.Request(
    "http://localhost:8000/query",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
)

with urllib.request.urlopen(req, timeout=10) as r:
    data = json.load(r)

answer = (data.get("answer") or "")[:200]
citations = data.get("citations") or []

print("Answer (first 200 chars):")
print(answer)
print("Citations returned:", len(citations))

if len(citations) < 1:
    sys.exit("Expected at least 1 citation")
PY
        '''
      }
    }

    stage('Deploy') {
      steps {
        sh '''
          set -e
          if docker compose version >/dev/null 2>&1; then
            COMPOSE="docker compose"
          else
            COMPOSE="docker-compose"
          fi
          $COMPOSE -f "$COMPOSE_FILE" up -d --build backend frontend
        '''
      }
    }
  }

  post {
    always {
      sh '''
        if docker compose version >/dev/null 2>&1; then
          COMPOSE="docker compose"
        else
          COMPOSE="docker-compose"
        fi
        $COMPOSE -f "$COMPOSE_FILE" ps || true
        $COMPOSE -f "$COMPOSE_FILE" logs --tail 200 backend || true
      '''
    }
  }
}
