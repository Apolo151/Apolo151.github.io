---
title: "A race condition in the competition judge, and leading the team behind it"
draft: true
# DRAFT, not built: waits for one confirmed figure for the teams that used the judge (or none),
# the test-race count, and the owner's own account of the leadership side.
category: "Debugging and leadership"
role: "Technical Team Head, STP"
weight: 4
summary: "The simulation judge for Machathon 5.00 lost track of cars at the start of their second lap."
problem: |
  For Machathon 5.00, an autonomous car racing competition, I built the ROS 2 and Gazebo judge for the simulation phase. Competing teams used it as the source of truth for lap times. Position tracking failed exactly at the start of a car's second lap.
decision: |
  I added logging to trace the failure and found a synchronisation conflict: the ROS 2 subscriber was destroyed while Gazebo was still removing the entity asynchronously, which left a short window where the respawned vehicle lost its odometry connection. I added synchronisation delays and state checks so the environment is fully cleaned up before the sensors start again.
result: |
  Lap times were recorded correctly across test runs, and the simulation-phase teams used the judge.
---
