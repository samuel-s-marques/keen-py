from src.core.base_module import BaseModule
from src.utils.print_utils import error, success

HASH_ALGORITHMS = {
    32: "MD5",
    40: "SHA-1",
    64: "SHA-256",
    128: "SHA-512",
}


class HashLookup(BaseModule):
    metadata = {
        "name": "Hash_Lookup",
        "description": "Identifies a hex-encoded hash's algorithm (MD5/SHA-1/SHA-256/SHA-512) and adds it to the graph for reputation pivoting.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "magic_consumes": ["x-hash"],
        "options": {
            "TARGET": [
                "",
                True,
                "The hash to identify (MD5, SHA-1, SHA-256, or SHA-512).",
                "hash",
            ],
        },
    }

    lower_target: bool = False

    def loading_message(self, target: str) -> str:
        return f"Identifying hash {target}..."

    async def execute(self, target: str) -> None:
        hash_value = target.strip()
        algorithm = HASH_ALGORITHMS.get(len(hash_value))

        if not algorithm:
            error(f"Unrecognized hash length for {hash_value}.")
            return

        success(f"{hash_value} identified as {algorithm}.")
        self.display_results(hash_value, algorithm)
        await self._save_results(hash_value, algorithm)

    def display_results(self, hash_value: str, algorithm: str) -> None:
        table = self.kv_table(title="Hash Identification")
        table.add_row("Hash", hash_value)
        table.add_row("Algorithm", algorithm)
        self.render(table)

    async def _save_results(self, hash_value: str, algorithm: str) -> None:
        from src.core.result_builder import NodeFactory, ResultBuilder

        builder = ResultBuilder()
        builder.add_node(
            NodeFactory.custom(
                stix_type="x-hash",
                value=hash_value,
                node_type="x-hash",
                misp_type=algorithm.lower().replace("-", ""),
                stix2_extra={"hashes": {algorithm: hash_value}},
                algorithm=algorithm,
            )
        )

        await self.post_run(builder.build())
