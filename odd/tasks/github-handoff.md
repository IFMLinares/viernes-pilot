# GitHub handoff / Entrega a GitHub
Objective / Objetivo: preserve the experimental planner and organize unresolved behavior into reviewable work, not declare it stable.
Branch: `chore/github-organization`; delivery: organization PR, then a draft feature-branch chain toward `main`; checks: structural validation and isolated Python tests, no live inference.

## Specs
- S1: User request: "Ok podemo smover todo esto al github? haciendo todo correctamente abriendo PR a la rama main y abriendo los issues nuevos? COn explicacion ingles/español para ir trabajando todo parte por aprte". Publish bilingual issues and PR explanations in English and Spanish.
- S2: User approved "Si, hazlo" after the proposal for organization first and a planner PR chain, separating voice, models and binaries. Preserve the original working tree and its unrelated local edits. Do not publish personal configuration, databases or private diagnostics.
- S3: User instruction: "No quiero añadirla manualemnte, no estoy añadiendo data real, estoy probando y debe funcionar bien! no solo por salir dle paso!". Issues must track actual conversational failures and acceptance criteria. Manual insertion and passing mocks are not proof of conversational correctness.
- S4: No automatic merge, issue approval, defect closure or claim of live-model stability. Use a draft integration tracker; keep behavior, tests and documentation together in dependent review units.

## Tasks
- T1 | S1,S2,S4 | inline | completed | commit 3da687c, organization issue #1 and PR #2; two forms and eleven controls structurally checked.
- T2 | S1,S3 | inline | completed | all-state duplicate search initially empty; bounded bilingual issues #3–#6 plus publication work item #7 created and read back.
- T3 | S1,S2,S4 | inline | in progress | tracker #8 and children #9–#12 published in draft; later cohesive units await explicit size decision, not cosmetic splitting.
- T4 | S1–S4 | inline | in progress | identities, bases, labels and body readback confirmed per creation; final linkage and limits being recorded.

## Log
- L1: The target is the public repository `github.com/IFMLinares/viernes-pilot`, default branch `main`. The active GitHub account has repository administration permission. Initial all-state discovery found no issues or PRs and no default-branch issue forms or PR template.
- L2: The original development branch contains unrelated voice/model assets and experimental planner changes. Publication uses isolated worktrees based on `origin/main`; no original history is rewritten and no assets are copied into the planner chain.
- L3: The selected strategy is a feature-branch chain: a draft integration PR targets `main`, the first child targets that tracker branch, and later children target the immediate parent. Nothing is merged automatically.
- L4: Existing target labels are the standard GitHub labels. This bootstrap adds forms using existing `bug` and `enhancement` labels; it adds no CI, approval labels or merge gates.
- L5: Forms may be used as the explicit source for CLI-rendered issue bodies from the bootstrap branch while its PR is unmerged. GitHub's default-branch issue UI receives them only after a separately authorized merge. The bootstrap PR does not claim to fix planner bugs.
- L6: Confirmed artifacts: organization #1/PR #2; capture lifecycle #3; extraction/provenance #4; date contracts #5; bounded acceptance #6; publication #7; draft tracker #8 toward main. Existing labels only; all issues remain open, no approval or merge performed.
- L7: Published chain: #9 runtime (247 additions, 9 focused tests), #10 storage (209 additions, 13 cumulative tests), #11 engine (391 additions, 25 cumulative tests), #12 CLI (108 changed lines, 28 cumulative tests). Each child targets its immediate predecessor; behavior, tests and bilingual documentation stay together. Source modules retain their original work-unit blobs; the CLI ports only the final dispatch, not unrelated voice changes.
- L8: The later candidate is preserved at branch `feat/planner-candidate-snapshot`, commit 54bd699, with an explicit no-direct-merge notice. It is an archive, not a review PR or stable release. Its isolated suite passes 225 tests (the 221 candidate cases plus four storage-library cases). Voice/model assets, personal configuration, databases, private task logs and historical reports are excluded. Real-model correctness remains unverified and reported failures stay open.
- L9: One honest historical sizing pass identifies cohesive over-budget units: bilingual presentation 490 changed lines, scoped queries 420, request diagnostics 659, parse metadata 482, comparison/corpus 482, evaluation CLI 1091 and offline rescoring 847. These counts describe the original work units, not a promise that a later port has exactly the same diff. Publish no over-budget review unit without the maintainer's explicit size decision; add no approval/exception label automatically.
- L10: Bounded independent CLI check passed 28 tests and exact legacy AST equality outside final dispatch. Parent repeated the command, verified committed bytes match staged bytes, and performed no live model/service calls. The archive suite also uses synthetic data and mocked transport, not live acceptance. Main and known defect issues remain unchanged.

## Español

La implementación conversacional sigue siendo experimental. Se conserva el trabajo existente sin mezclar modelos o binarios de voz. Los informes distinguirán hechos observados de causas todavía no verificadas, y las pruebas simuladas de la aceptación con el modelo real.

El PR de organización no agrega reglas de aprobación ni automatizaciones. Los formularios estarán disponibles en la interfaz de nuevas issues cuando se integre ese PR en `main`; su contenido puede usarse explícitamente para preparar las issues mediante la CLI antes de esa integración.
