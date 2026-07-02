# Three Estates Simple Memory Fork

Run from the repository root with:

```bash
python3 three_estates_sim_simple/server.py
```

This fork is intentionally simpler than `three_estates_sim`:

- Agents keep a perfect runtime transcript of events/dialogue they personally perceived or overheard.
- Event/chat nodes are not persisted as associative memory.
- Poignancy scoring does not drive memory or reflection.
- Semantic RAG retrieval is not used for prompt context.
- Reflection is triggered by actual movement count via `THREE_ESTATES_MOVEMENT_REFLECTION_TRIGGER_COUNT` (default `3`).
- Only reflection thought nodes are persisted in `associative_memory/nodes.json`.
- Persisted reflection thoughts are recalled only through direct keyword matching.
