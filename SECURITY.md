# Security

## No-prompt execution

This template deliberately launches Codex and Claude Code with permission checks bypassed. A compromised dependency, malicious repository instruction, or prompt injection could therefore execute commands with the current user's privileges.

Use the live loop only when all of the following are true:

- You trust the repository and its instructions.
- You reviewed the objective for untrusted pasted content.
- The machine or container contains no unrelated secrets or valuable writable data.
- Git provides a recoverable record of the starting state.
- You understand that repository instructions are behavioral guidance, not a security sandbox.

For stronger isolation, run the template inside an ephemeral container or virtual machine with scoped credentials and network controls.

## Secret handling

The coordinator stores prompts, responses, and logs under `.agent-loop/`. This directory is ignored by Git, but it remains on disk. Never include secrets in objectives or agent handoffs. Delete local session data according to your own retention policy.

## Reporting

Open a GitHub security advisory for vulnerabilities. Do not include live credentials, private transcripts, or personal data in a public issue.
