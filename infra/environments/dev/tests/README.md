# dev root static tests

These tests require Python, pytest, and Hypothesis. They do not invoke Terraform, contact AWS, read credentials, or create resources. The Task 4 pipeline contract test reads the bootstrap files statically; it does not execute their buildspec commands.

After installing the pinned local test dependencies, run the complete dev suite from the repository root:

```bash
python3 -m pip install -r infra/environments/dev/tests/requirements.txt
python3 -m pytest infra/environments/dev/tests -q
```

`test_naming_property.py` contains concrete unit cases, Property 11 with 100 Hypothesis examples, and a Terraform/Python naming consistency check. `test_pipeline_contract.py` verifies the Task 4 ownership boundary: bootstrap owns CodePipeline/CodeBuild/IAM, while the dev root owns the Terraform root, backend contract, and module wiring.

The static module snapshots are in `infra/modules/network/tests/` and `infra/modules/ecr/tests/`; they use the same installed pytest dependency and can be run without Terraform or AWS access.
