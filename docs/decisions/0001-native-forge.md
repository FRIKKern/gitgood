# Native forge

Status: accepted in the design conversation, 7 October 2026.

Gitgood owns its forge backend and data model. Use standard Git for repository storage/operations. Forgejo remains a reference, not the production engine.

This accepts responsibility for transport authorization, reviews, branch policy, merges, concurrent operations, and recovery. It does not require writing every library ourselves or bypassing supported Barkpark capabilities.

Consequences: prioritize correctness experiments and a small complete release. Do not reopen the native decision without a material finding and an explicit product decision. Other design choices remain open in the decision index.
