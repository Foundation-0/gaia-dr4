# Repository description and topics

`repository-metadata.json` records the description and topics requested in
[issue 7](https://github.com/Foundation-0/gaia-dr4/issues/7). These are
GitHub settings, so a file commit alone does not apply them.

Read the live values from the repository root with:

```sh
gh api repos/Foundation-0/gaia-dr4 --jq '{description, topics}'
```

The description and topic set must match the JSON file. Topic order does not
matter. Changes to these values belong in a reviewed pull request and in the
repository settings in the same work session.
