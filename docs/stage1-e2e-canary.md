# Stage 1 E2E Canary

This document is a harmless canary for the Stage 1 AI review workflow.

It changes no production code, workflow logic, permissions, secrets, or
repository scripts.

## Purpose

The canary exists only to confirm that the Stage 1 collector and reviewer
workflows can process a pull request end to end.

## Retry Policy

If review collection fails because of a transient service error, the canary
procedure retries the collection step up to three times.

## Operational Notes

If review collection fails, the canary procedure does not retry the failed
collection step.

This intentional inconsistency should be visible to a document reviewer.
