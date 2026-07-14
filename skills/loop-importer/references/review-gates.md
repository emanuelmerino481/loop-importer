# Human review gates

Approve an import only after checking:

1. Project root and Git commit identify the intended working version.
2. Dirty files are explained and either captured or excluded intentionally.
3. Formal data inputs have version IDs or hashes computed by an approved data workflow.
4. Training, inference, evaluation, and reporting entrypoints are confirmed from commands or logs.
5. The primary metric, statistical unit, aggregation, threshold, and uncertainty method are frozen.
6. Every formal seed is listed; failed seeds remain part of the record.
7. Baseline and best-known results link to code, config, checkpoint, and raw evaluator output.
8. GPU type, count, precision, batch probes, budget, and stop conditions are explicit.
9. Protected paths and tools are encoded in Task Envelopes.
10. No lexical task dependency is promoted as fact without independent evidence.
