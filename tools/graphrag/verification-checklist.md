# GraphRAG Verification Checklist

Do not claim GraphRAG is implemented unless these are true.

## Ingestion

- [ ] docs are parsed into DocPage/DocSection nodes
- [ ] code is parsed into CodeFile/Function/Class nodes
- [ ] tests are parsed into TestFile/TestCase nodes
- [ ] feature packets are indexed
- [ ] frontmatter metadata is indexed

## Edges

- [ ] Feature -> Requirement
- [ ] Requirement -> AcceptanceCriterion
- [ ] Feature -> Docs
- [ ] Feature -> Code
- [ ] Code -> Tests
- [ ] UIFlow -> E2E tests
- [ ] API -> Endpoint handlers
- [ ] DocSection -> CodeFile/Symbol

## Retrieval

- [ ] feature context retrieval works
- [ ] symbol lookup works
- [ ] related tests retrieval works
- [ ] docs-for-code retrieval works
- [ ] code-for-doc retrieval works
- [ ] stale docs detection exists or is planned

## Agent usage

- [ ] AGENTS.md tells agents to use GraphRAG/MCP before broad reads
- [ ] fallback behavior exists if GraphRAG is unavailable
- [ ] retrieval logs are stored
- [ ] token usage is measured
