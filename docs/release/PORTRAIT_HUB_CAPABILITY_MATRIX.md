# Portrait Hub capability disposition

The source anchor is `source-manifest.json`. API path compatibility is not an
acceptance criterion. Each migrated capability must be reachable through a
Scenara domain plugin and the public Media/Run/Result contracts.

| Capability | Disposition | Scenara evidence |
|---|---|---|
| Image validation and decoding | reimplemented | `scenara.platform.media` |
| Person detection | migrated | Portrait plugin operator and contract test |
| Body ReID | reimplemented | portrait.analysis backend contract; production rejects a missing licensed OSNet package |
| Face detection/alignment/embedding | reimplemented | typed face objects, relations, recursive embedding redaction, and production model gate |
| Pose | reimplemented | portrait.analysis pose attributes; approved RTMPose package and fixed evaluation remain release gates |
| Human parsing and apparel attributes | reimplemented | typed capability and explicit development-substitute provenance |
| Silhouette segmentation | reimplemented | typed silhouette objects and relations; production rejects the bbox substitute |
| Gait | reimplemented | sequence-only contract enforces at least eight frames and records model provenance |
| Gallery identity and search | reimplemented | tenant identity/enrollment/search APIs, feature-space isolation, and biometric deletion test |
| Long-video tracking | reimplemented | batch media units, track contract, result sharding, and dedicated worker lane |
| In-video person tracklets | reimplemented | two-stage association, global assignment, fragment reconnection with time-compatibility, tracklet quality scoring, and handoff into long-term identity registration |
| Cross-camera long-term trajectory | reimplemented | face + body fusion, camera topology and mutual-exclusion constraints, real media timeline, capped template galleries, human adjudication (confirm/reject/rename/merge/split/delete), and cross-video identity persistence/query closure |
| Camera registry and topology | reimplemented | tenant-scoped camera records, automatic source-camera registration, and minimum/maximum transition times enforced during Re-ID |
| Real-time stream processing | reimplemented | encrypted credentials, bounded decode, stream queue lane, and termination reason contract |
| Legacy `/v1` API compatibility | explicitly retired | new API is `/api/v1` |
| Legacy database and development data | explicitly retired | clean migration revision |
| Legacy release and generated SDK artifacts | explicitly retired | source manifest exclusion |

