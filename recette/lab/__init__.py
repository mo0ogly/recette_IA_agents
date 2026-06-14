"""Simulated lab: deterministic mock doubles of the 11 external systems.

Zero real side effects, zero real tokens. One generic HTTP server dispatches
POST /{target_system}/execute to per-domain pure handlers (lab/domains/*).
"""
