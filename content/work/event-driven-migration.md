---
title: "Breaking up a monolith into event-driven services"
category: "Architecture"
role: "Team lead: system design and infrastructure"
team: "Graduation project team"
date: 2025-10-01
weight: 2
summary: "DabljaAR dubs English videos into Arabic. I led the design and the migration with the team, from a FastAPI monolith to event-driven services on RabbitMQ."
problem: |
  DabljaAR, our graduation project, dubs English videos into Arabic: speech-to-text, then translation, then text-to-speech, then merging the result back into the video. The first version was a FastAPI modular monolith with Celery workers on Redis.
decision: |
  The pipeline became an orchestrator plus speech-to-text, translation, text-to-speech, media and merge services, each consuming its own stage from RabbitMQ; an intermediate version used gRPC.

  As team lead I owned the system design and all the infrastructure, and I led the design and the migration with the team. Teammates implemented parts of it, for example the Go orchestrator.
result: |
  The code is in the [public repository](https://github.com/DabljaAR/web). On the infrastructure side I set up service-level indicators and objectives with Prometheus and Grafana, distributed tracing with OpenTelemetry and Jaeger, security-scanning CI and a GitOps workflow.
---
