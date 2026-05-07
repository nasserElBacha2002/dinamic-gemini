# architecture-migration-plan

**ROLE**  
You are a senior software architect designing an incremental architecture migration for a v3 inventory operations platform with backend, frontend, SQL Server persistence, and a CV/LLM processing pipeline.

**PRIMARY GOAL**  
Create a safe, incremental migration plan for a major architecture change. Do not implement code.

**CONTEXT**  
The system currently uses generic inventories, generic prompts, provider/model-specific prompt logic, and reference images tied to the current inventory/pasillo flow.

The new product direction is client-specific customization:

- Add Clients.
- Each Client has Suppliers.
- Each Client Supplier has its own reference images.
- Each Client Supplier has editable prompt instructions.
- Prompt output-contract instructions must remain protected.
- Provider/model adapters must continue handling normalization.
- Inventories must belong to Clients.
- Aisles must belong to a Supplier of the Inventory’s Client.

**STRICT RULES**

- Do not modify code.
- Do not create migrations.
- Do not change files.
- Do not propose a big-bang rewrite unless unavoidable.
- Preserve legacy data.
- Preserve existing API behavior until replacement paths are ready.
- Keep the migration incremental and testable.

**TASKS**

1. Inspect the current architecture:
   - inventory model
   - aisle model
   - source assets
   - reference images
   - prompt composition
   - prompt hardcoding
   - provider adapters
   - pipeline execution
   - repositories
   - migrations
   - frontend creation flows

2. Design target architecture:
   - clients
   - client_suppliers
   - supplier_reference_images
   - supplier_prompt_configs
   - prompt_templates or protected system prompt definitions
   - inventory.client_id
   - aisle.client_supplier_id

3. Design prompt architecture:
   - protected system instructions
   - provider adapter instructions
   - editable supplier instructions
   - inventory context
   - aisle context
   - reference image context

4. Design migration strategy:
   - legacy/default client
   - legacy/default suppliers
   - mapping existing inventories
   - mapping existing reference images
   - preserving old prompts
   - phased deprecation of old flows

5. Design implementation phases:
   - phase name
   - goal
   - scope
   - files likely affected
   - data changes
   - API changes
   - frontend changes
   - tests
   - validation commands
   - rollback/compatibility notes

**OUTPUT FORMAT**

Return:

1. Executive summary  
2. Current-state architecture  
3. Target-state architecture  
4. Data model proposal  
5. Prompt architecture proposal  
6. Adapter/normalization preservation strategy  
7. API migration strategy  
8. Frontend migration strategy  
9. Legacy data migration strategy  
10. Suggested phases  
11. DoD per phase  
12. Risks and mitigations  
13. Open questions  
14. Recommended first implementation phase

**IMPORTANT**  
No code changes. This is a planning command only.