---
title: "Moving a provisioning platform off a single EC2 box to Kubernetes on EKS"
category: "Platform migration"
role: "Cloud Engineering Intern, Obelion.ai"
team: "About 8 contributors to the infrastructure repository"
date: 2024-12-01
weight: 1
summary: "A cloud-provisioning platform ran on one EC2 instance with Docker-in-Docker. I designed how it would run on Kubernetes on AWS EKS, built my part of the new platform."
problem: |
  The company's cloud-provisioning platform ran on a single EC2 instance with a Docker-in-Docker setup.
decision: |
  Move the platform to Kubernetes on AWS EKS. I wrote the migration design for the engine: it creates Kubernetes Jobs instead of running Docker inside Docker, with RBAC for the service account that creates them, Secrets for cloud credentials and shared EFS volumes through persistent volume claims, all from templated manifests. I prototyped job creation with the official Node client and wrote a usage guide for the backend engineers.

  Around it I built an HA RabbitMQ cluster with the RabbitMQ operator and Kustomize overlays, and Terraform modules for RDS and Amazon MQ.
result: |
  Everything I built was merged to main.
---
