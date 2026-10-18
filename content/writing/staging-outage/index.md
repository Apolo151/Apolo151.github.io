---
title: "Recurring staging outages: write-up coming"
date: 2026-10-18
categories: ["postmortems"]
language: en
description: "A short note on recurring staging outages caused by a full disk, with the full postmortem to follow."
---
A staging environment kept going down. The logs showed the cause: Docker images from CI builds, multi-gigabyte AI/ML images, were filling the disk.

A scheduled cleanup fixed it, and no further outage followed.

The full postmortem is coming.
