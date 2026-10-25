import pandas as pd
import pytest

import eda_queries


def _df(columns: str, *rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=columns.split())


@pytest.fixture
def tiny_data() -> dict[str, pd.DataFrame]:
    """Every dataset in eda_queries.DATASETS with its real columns, at toy size.

    Edge cases kept on purpose: a degree-0 gene, a disease with 0 treatments,
    compound/disease pairs with 0 paths, and one property that only some labels have.
    """
    data = {
        "node_counts": _df("label n_labels n", ("Compound", 1, 3), ("Disease", 1, 3), ("Gene", 1, 4)),
        "edge_counts": _df(
            "rel_type src dst n n_unbiased",
            ("ASSOCIATES_DaG", "Disease", "Gene", 40, 10),
            ("BINDS_CbG", "Compound", "Gene", 30, 0),
            ("INTERACTS_GiG", "Gene", "Gene", 100, 0),
            ("PALLIATES_CpD", "Compound", "Disease", 2, 0),
            ("RESEMBLES_CrC", "Compound", "Compound", 6, 0),
            ("TREATS_CtD", "Compound", "Disease", 3, 1),
        ),
        "degrees": _df(
            "label id name degree",
            ("Compound", "DB1", "Alpha", 20), ("Compound", "DB2", "Beta", 5),
            ("Compound", "DB3", "Gamma", 1),
            ("Disease", "DOID:1", "asthma", 30), ("Disease", "DOID:2", "gout", 8),
            ("Disease", "DOID:3", "flu", 2),
            ("Gene", "1", "G1", 50), ("Gene", "2", "G2", 12), ("Gene", "3", "G3", 3),
            ("Gene", "4", "G4", 0),
        ),
        "rel_coverage": _df(
            "rel_type src dst n_src n_dst",
            ("ASSOCIATES_DaG", "Disease", "Gene", 3, 3),
            ("BINDS_CbG", "Compound", "Gene", 2, 2),
            ("INTERACTS_GiG", "Gene", "Gene", 3, 3),
            ("PALLIATES_CpD", "Compound", "Disease", 1, 1),
            ("RESEMBLES_CrC", "Compound", "Compound", 3, 3),
            ("TREATS_CtD", "Compound", "Disease", 2, 2),
        ),
        "node_props": _df(
            "label property n_present n_empty",
            ("Compound", "name", 3, 0), ("Compound", "inchi", 3, 1),
            ("Disease", "name", 3, 0),
            ("Gene", "name", 4, 0), ("Gene", "chromosome", 4, 1),
        ),
        "node_sources": _df(
            "label source license n",
            ("Compound", "DrugBank", "CC0", 3), ("Disease", "Disease Ontology", "CC0", 3),
            ("Gene", "Entrez Gene", "CC0", 4),
        ),
        "edge_sources": _df(
            "rel_type source unbiased n",
            ("ASSOCIATES_DaG", "DISEASES", False, 30), ("ASSOCIATES_DaG", "GWAS", True, 10),
            ("TREATS_CtD", "PharmacotherapyDB", True, 1),
        ),
        "treatments": _df(
            "compound compound_name disease disease_name rel_type",
            ("DB1", "Alpha", "DOID:1", "asthma", "TREATS_CtD"),
            ("DB1", "Alpha", "DOID:2", "gout", "TREATS_CtD"),
            ("DB2", "Beta", "DOID:1", "asthma", "TREATS_CtD"),
            ("DB2", "Beta", "DOID:2", "gout", "PALLIATES_CpD"),
            ("DB3", "Gamma", "DOID:1", "asthma", "PALLIATES_CpD"),
        ),
        "disease_profile": _df(
            "disease name genes treats palliates symptoms anatomies similar",
            ("DOID:1", "asthma", 20, 2, 1, 5, 4, 2),
            ("DOID:2", "gout", 10, 1, 1, 3, 2, 1),
            ("DOID:3", "flu", 4, 0, 0, 2, 1, 0),
        ),
        "compound_profile": _df(
            "compound name binds side_effects treats palliates resembles classes up down",
            ("DB1", "Alpha", 5, 200, 2, 0, 3, 2, 1, 0),
            ("DB2", "Beta", 2, 30, 1, 1, 2, 1, 0, 0),
            ("DB3", "Gamma", 0, 0, 0, 1, 1, 0, 0, 0),
        ),
        "gene_profile": _df(
            "gene name chromosome interacts bound_by diseases processes",
            ("1", "G1", "1", 50, 4, 9, 20), ("2", "G2", "X", 12, 0, 3, 5),
            ("3", "G3", "2", 3, 1, 1, 0), ("4", "G4", "2", 0, 0, 0, 0),
            ("5", "G5", "3", 7, 2, 2, 1), ("6", "G6", "3", 9, 3, 1, 2),
        ),
        "symmetry": _df(
            "rel_type self_loops reciprocal_pairs parallel_pairs",
            ("INTERACTS_GiG", 0, 0, 0), ("RESEMBLES_CrC", 0, 0, 0),
        ),
        "conflicting_regulation": _df(
            "source_label pairs entities", ("Compound", 0, 0), ("Disease", 0, 0),
        ),
        "edge_numeric": _df(
            "rel_type property value",
            *[("RESEMBLES_CrC", "similarity", v) for v in (0.5, 0.6, 0.7, 1.0)],
            *[("UPREGULATES_CuG", "z_score", v) for v in (4.1, 5.0, 9.0, 20.0)],
        ),
        "pharm_classes": _df(
            "name class_type n_compounds",
            ("A", "Mechanism of Action", 1), ("B", "Mechanism of Action", 3),
            ("C", "Physiologic Effect", 2),
        ),
        "cbgad_paths": _df(
            "compound disease paths",
            ("DB1", "DOID:1", 3), ("DB1", "DOID:2", 1), ("DB2", "DOID:1", 2),
        ),
        "crctd_paths": _df(
            "compound disease paths",
            ("DB2", "DOID:1", 1), ("DB3", "DOID:2", 2), ("DB1", "DOID:2", 1),
        ),
    }
    assert set(data) == set(eda_queries.DATASETS)
    return data
