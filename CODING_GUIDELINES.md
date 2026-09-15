Write code with the discipline of Gerard Holzmann and document it with the clarity of George Orwell.

## Core Principles

- Prefer simple, explicit, verifiable code over clever code.
- Make control flow, state changes, assumptions, and failure modes easy to see.
- Write documentation and comments in plain, direct English.
- Optimize first for correctness and maintainability, then for brevity or performance.
- Follow the project's established language, style, tests, and tooling unless they conflict with correctness.

## Code: Gerard Holzmann

### Keep Control Flow Simple

- Keep control flow linear where possible.
- Avoid more than two levels of nesting. Use guard clauses, early returns, or small helper functions to flatten complex logic.
- Give each function one clear job.
- Keep functions short enough to understand at a glance, usually no more than about 60 lines.
- Avoid recursion unless it is clearly safer and simpler than iteration and has a proven depth bound.

### Bound Work and Resource Use

- Give every loop an explicit, defensible termination condition.
- Put clear limits on retries, queue sizes, recursion depth, input sizes, and memory growth.
- Do not rely on claims such as "this will never get large" without enforcing the limit in code.
- Reject or safely handle input that exceeds defined limits.

### Manage Resources Correctly

- Close or release every resource that the code opens or acquires.
- Handle cleanup on success, failure, cancellation, and early-return paths.
- Prefer language constructs that guarantee cleanup, such as context managers, `defer`, RAII, or `finally`.

### Fail Clearly

- Never swallow an error.
- Handle an error, add useful context and propagate it, or fail explicitly.
- Do not use empty catch blocks or broad exception handling without a specific reason.
- Preserve the original cause when wrapping or rethrowing an error.
- Write error messages that state what failed and include the context needed to diagnose it.

### Make Assumptions Executable

- Use assertions for genuine internal invariants and programmer errors.
- Validate external input with normal error handling, not assertions.
- Add assertions where they expose important preconditions, postconditions, state transitions, or impossible cases.
- Do not add arbitrary or redundant assertions merely to meet a quota.

### Maintain a Clean Build

- Treat compiler, type-checker, linter, and static-analysis warnings as defects.
- Keep the warning count at zero from the start.
- Do not suppress a warning unless the code documents why suppression is safe and necessary.

## Code Comments

Comment the code so a reader can understand the purpose of each logical section without reconstructing the entire algorithm.

### Comment Each Significant Section

- Place a short comment before each non-obvious logical section or phase.
- Explain what the section is trying to achieve and why it exists.
- Mark important stages such as validation, normalization, transformation, persistence, cleanup, and error recovery.
- For complex algorithms, explain the invariant or strategy before the relevant block.
- Keep comments close to the code they describe.

Example:

```python
# Reject malformed records before changing shared state.
validated_records = validate(records)

# Apply the complete batch atomically so readers never observe partial results.
with database.transaction():
    database.insert_all(validated_records)
```

### Explain Why, Not Syntax

- Do not restate an obvious line of code.
- Explain intent, constraints, trade-offs, assumptions, and surprising behavior.
- Document why an unusual implementation is necessary.
- State units, limits, ownership, thread-safety expectations, and side effects when they are not obvious.
- If code needs a long comment to explain what it does, first try to make the code simpler.

Poor:

```python
# Increment the retry count.
retry_count += 1
```

Better:

```python
# Count this attempt before the backoff check so the total cannot exceed the configured limit.
retry_count += 1
```

### Keep Comments Accurate

- Update comments when behavior changes.
- Delete stale, misleading, or redundant comments.
- Do not leave commented-out code; version control already preserves history.
- Make TODO comments specific: state what remains, why it matters, and any relevant issue reference.

## Documentation: George Orwell

Apply Orwell's rules to comments, docstrings, READMEs, API documentation, commit messages, and error messages.

- Use familiar, concrete words.
- Prefer short words when they are equally precise.
- Cut every word that adds no meaning.
- Prefer active voice.
- Avoid clichés, stock metaphors, jargon, and unexplained abbreviations.
- Use a technical term only when it is more precise than everyday English; define it when readers may not know it.
- Break any rule when following it would make the writing less clear or less accurate.

### Document Public Behavior

For public functions, classes, modules, commands, and APIs, document:

- What the code does.
- What inputs it accepts and what outputs it returns.
- Units, valid ranges, defaults, and limits.
- Side effects and external resources it uses.
- Errors it can return or raise.
- Any ordering, concurrency, security, or performance guarantees callers rely on.

Do not document implementation details as if they were stable guarantees.

## Tests and Verification

- Test normal behavior, boundary conditions, invalid input, and failure paths.
- Add a regression test for every bug fix when practical.
- Verify cleanup and partial-failure behavior for code that manages resources or writes state.
- Keep tests deterministic and bounded.
- Run the relevant formatter, linter, type checker, tests, and build before declaring work complete.
- Report anything that could not be verified.

## Final Review Checklist

- Is the control flow simple and shallow?
- Is every loop, retry, allocation, and recursive path bounded?
- Are resources released on every path?
- Are errors handled or propagated with useful context?
- Do assertions enforce meaningful internal invariants?
- Does the code build without warnings?
- Does each significant, non-obvious section have a concise comment explaining its purpose?
- Do comments explain why rather than repeat what the code says?
- Is all documentation plain, active, concise, and precise?
- Do tests cover boundaries and failures as well as the happy path?
