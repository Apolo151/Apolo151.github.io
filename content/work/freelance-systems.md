---
title: "Freelance systems: a legacy replacement and a multi-hotel PMS"
category: "Freelance"
role: "Freelance full-stack engineer"
date: 2025-05-01
weight: 3
summary: "Two client systems: a replacement for a tourist-village management system more than 20 years old, which I ran end to end from requirements to launch, and a multi-hotel property management system I built."
problem: |
  Two client projects. One replaced a tourist-village management system more than 20 years old. The other was a multi-hotel property management system, with audit logging and two-way sync with a channel manager.
decision: |
  I gathered requirements with clients who are not technical, through user stories, a terminology spec and feedback rounds in Arabic and English.

  The village system became an Express and TypeScript app on PostgreSQL with a React frontend, covering bookings, owner and renter accounting, services, invoices and occupancy reports. For the hotel system I built two-way sync with a channel manager on RabbitMQ, with role-based access scoped to each hotel and audit logging.
result: |
  The new village system replaced the legacy one, and I supported it after launch. I added trigram and composite indexes and server-side pagination, tested with 200+ generated records per entity. I documented the systems (ERD, use cases, a gap report and spec-driven plans) and set up Docker, Caddy and Terraform deployment.
---
