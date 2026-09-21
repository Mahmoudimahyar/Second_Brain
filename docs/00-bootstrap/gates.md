# Build Gates

Coding must not start until these gates pass.

## 1. PRD Gate

- [ ] Product summary exists
- [ ] Target users defined
- [ ] MVP scope defined
- [ ] Out-of-scope list defined
- [ ] User journeys defined
- [ ] Functional requirements defined
- [ ] Non-functional requirements defined
- [ ] Acceptance criteria are testable
- [ ] Blocking questions tracked

## 2. Architecture Gate

- [ ] Tech stack selected
- [ ] Architecture documented
- [ ] Module boundaries documented
- [ ] Dependency rules documented
- [ ] Data model drafted
- [ ] API strategy drafted
- [ ] Auth/security strategy drafted
- [ ] Deployment strategy drafted
- [ ] ADRs written for major decisions

## 3. Feature Packet Gate

For the first vertical slice:
- [ ] README.md
- [ ] requirements.md
- [ ] api.md
- [ ] data.md
- [ ] ui-flow.md if UI
- [ ] state-machine.md if stateful
- [ ] test-plan.md
- [ ] context.md
- [ ] plan.md

## 4. Test Gate

- [ ] Unit tests identified
- [ ] Integration tests identified
- [ ] Contract tests identified
- [ ] E2E/browser tests identified
- [ ] Browser console/network checks defined
- [ ] Required test data/fixtures defined

## 5. Environment Gate

- [ ] All required env vars listed in .env.example
- [ ] User knows which values to provide
- [ ] No real secrets committed
- [ ] Missing optional integrations documented
