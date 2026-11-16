# GitHub handoff / Entrega a GitHub
Objective / Objetivo: preserve the experimental planner and organize unresolved behavior into reviewable work, not declare it stable.
Branch: `chore/github-organization`; delivery: organization PR, then a draft feature-branch chain toward `main`; checks: structural validation and isolated Python tests, no live inference.

## Specs
- S1: User request: "Ok podemo smover todo esto al github? haciendo todo correctamente abriendo PR a la rama main y abriendo los issues nuevos? COn explicacion ingles/español para ir trabajando todo parte por aprte". Publish bilingual issues and PR explanations in English and Spanish.
- S2: User approved "Si, hazlo" after the proposal for organization first and a planner PR chain, separating voice, models and binaries. Preserve the original working tree and its unrelated local edits. Do not publish personal configuration, databases or private diagnostics.
- S3: User instruction: "No quiero añadirla manualemnte, no estoy añadiendo data real, estoy probando y debe funcionar bien! no solo por salir dle paso!". Issues must track actual conversational failures and acceptance criteria. Manual insertion and passing mocks are not proof of conversational correctness.
- S4: No automatic merge, issue approval, defect closure or claim of live-model stability. Use a draft integration tracker; keep behavior, tests and documentation together in dependent review units.

## Tasks
- T1 | S1,S2,S4 | inline | in progress | bilingual issue forms and PR template; small independent organization change.
- T2 | S1,S3 | inline | pending | deduplicate and create bounded issues with exact reproduction and acceptance evidence.
- T3 | S1,S2,S4 | inline | pending | draft integration tracker and a single honest slicing pass; report cohesive over-budget units instead of cosmetic splitting.
- T4 | S1–S4 | inline | pending | verify remote identities/readback and summarize links, dependencies and limitations.

## Log
- L1: The target is the public repository `github.com/IFMLinares/viernes-pilot`, default branch `main`. The active GitHub account has repository administration permission. Initial all-state discovery found no issues or PRs and no default-branch issue forms or PR template.
- L2: The original development branch contains unrelated voice/model assets and experimental planner changes. Publication uses isolated worktrees based on `origin/main`; no original history is rewritten and no assets are copied into the planner chain.
- L3: The selected strategy is a feature-branch chain: a draft integration PR targets `main`, the first child targets that tracker branch, and later children target the immediate parent. Nothing is merged automatically.
- L4: Existing target labels are the standard GitHub labels. This bootstrap adds forms using existing `bug` and `enhancement` labels; it adds no CI, approval labels or merge gates.
- L5: Forms may be used as the explicit source for CLI-rendered issue bodies from the bootstrap branch while its PR is unmerged. GitHub's default-branch issue UI receives them only after a separately authorized merge. The bootstrap PR does not claim to fix planner bugs.

## Español

La implementación conversacional sigue siendo experimental. Se conserva el trabajo existente sin mezclar modelos o binarios de voz. Los informes distinguirán hechos observados de causas todavía no verificadas, y las pruebas simuladas de la aceptación con el modelo real.

El PR de organización no agrega reglas de aprobación ni automatizaciones. Los formularios estarán disponibles en la interfaz de nuevas issues cuando se integre ese PR en `main`; su contenido puede usarse explícitamente para preparar las issues mediante la CLI antes de esa integración.
