# Hetionet schema (auto-generated)

Server: `[['Neo4j Kernel', ['3.5.12'], 'community']]`


## Node labels

| Label | Count | Properties |
|---|---|---|
| Anatomy | 402 | license, mesh_id, source, url, name, identifier |
| BiologicalProcess | 11381 | license, name, url, identifier, source |
| CellularComponent | 1391 | license, name, url, identifier, source |
| Compound | 1552 | license, inchi, inchikey, source, url, identifier, name |
| Disease | 137 | license, source, url, identifier, name |
| Gene | 20945 | license, chromosome, source, url, description, identifier, name |
| MolecularFunction | 2884 | url, license, name, identifier, source |
| Pathway | 1822 | license, source, identifier, name |
| PharmacologicClass | 345 | class_type, license, source, url, identifier, name |
| SideEffect | 5734 | license, source, url, name, identifier |
| Symptom | 438 | license, name, source, identifier, url |

## Relationship types

| Type | Count | From -> To | Properties |
|---|---|---|---|
| ASSOCIATES_DaG | 12623 | Disease -> Gene | license, sources, unbiased |
| BINDS_CbG | 11571 | Compound -> Gene | sources, unbiased, actions, license, urls |
| CAUSES_CcSE | 138944 | Compound -> SideEffect | license, unbiased, source, url |
| COVARIES_GcG | 61690 | Gene -> Gene | source, unbiased |
| DOWNREGULATES_AdG | 102240 | Anatomy -> Gene | source, unbiased |
| DOWNREGULATES_CdG | 21102 | Compound -> Gene | unbiased, method, z_score, source |
| DOWNREGULATES_DdG | 7623 | Disease -> Gene | license, unbiased, log2_fold_change, source |
| EXPRESSES_AeG | 526407 | Anatomy -> Gene | license, sources, unbiased |
| INCLUDES_PCiC | 1029 | PharmacologicClass -> Compound | unbiased, source, license |
| INTERACTS_GiG | 147164 | Gene -> Gene | sources, unbiased |
| LOCALIZES_DlA | 3602 | Disease -> Anatomy | license, unbiased, source |
| PALLIATES_CpD | 390 | Compound -> Disease | license, unbiased, source |
| PARTICIPATES_GpBP | 559504 | Gene -> BiologicalProcess | unbiased, source, license |
| PARTICIPATES_GpCC | 73566 | Gene -> CellularComponent | unbiased, source, license |
| PARTICIPATES_GpMF | 97222 | Gene -> MolecularFunction | unbiased, source, license |
| PARTICIPATES_GpPW | 84372 | Gene -> Pathway | license, unbiased, source |
| PRESENTS_DpS | 3357 | Disease -> Symptom | license, unbiased, source |
| REGULATES_GrG | 265672 | Gene -> Gene | method, source, unbiased, subtypes |
| RESEMBLES_CrC | 6486 | Compound -> Compound | license, similarity, source, unbiased |
| RESEMBLES_DrD | 543 | Disease -> Disease | license, unbiased, source |
| TREATS_CtD | 755 | Compound -> Disease | license, unbiased, source |
| UPREGULATES_AuG | 97848 | Anatomy -> Gene | source, unbiased |
| UPREGULATES_CuG | 18756 | Compound -> Gene | unbiased, method, z_score, source |
| UPREGULATES_DuG | 7731 | Disease -> Gene | license, unbiased, log2_fold_change, source |

## One example node per label

- **Anatomy**: `{'license': 'CC BY 3.0', 'identifier': 'UBERON:0002352', 'mesh_id': 'D001283', 'name': 'atrioventricular node', 'source': 'Uberon', 'url': 'http://purl.obolibrary.org/obo/UBERON_0002352'}`
- **BiologicalProcess**: `{'license': 'CC BY 4.0', 'identifier': 'GO:0097343', 'name': 'ripoptosome assembly', 'source': 'Gene Ontology', 'url': 'http://purl.obolibrary.org/obo/GO_0097343'}`
- **CellularComponent**: `{'license': 'CC BY 4.0', 'identifier': 'GO:0022624', 'name': 'proteasome accessory complex', 'source': 'Gene Ontology', 'url': 'http://purl.obolibrary.org/obo/GO_0022624'}`
- **Compound**: `{'license': 'CC BY-NC 4.0', 'identifier': 'DB01148', 'inchikey': 'InChIKey=SPIUTQOUKAMGCX-UHFFFAOYSA-N', 'inchi': 'InChI=1S/C24H25NO4/c1-17-21(26)19-11-8-12-20(23(19)29-22(17)18-9-4-2-5-10-18)24(27)28-16-15-25-13-6-3-7-14-25/h2,4-5,8-12H,3,6-7,13-16H2,1H3', 'name': 'Flavoxate', 'source': 'DrugBank', 'url': 'http://www.drugbank.ca/drugs/DB01148'}`
- **Disease**: `{'license': 'CC BY 3.0', 'identifier': 'DOID:4606', 'name': 'bile duct cancer', 'source': 'Disease Ontology', 'url': 'http://purl.obolibrary.org/obo/DOID_4606'}`
- **Gene**: `{'license': 'CC0 1.0', 'identifier': 128239, 'chromosome': '1', 'name': 'IQGAP3', 'description': 'IQ motif containing GTPase activating protein 3', 'source': 'Entrez Gene', 'url': 'http://identifiers.org/ncbigene/128239'}`
- **MolecularFunction**: `{'license': 'CC BY 4.0', 'identifier': 'GO:0003884', 'name': 'D-amino-acid oxidase activity', 'source': 'Gene Ontology', 'url': 'http://purl.obolibrary.org/obo/GO_0003884'}`
- **Pathway**: `{'license': 'CC BY 4.0', 'identifier': 'PC7_2621', 'name': 'Class B/2 (Secretin family receptors)', 'source': 'Reactome via Pathway Commons'}`
- **PharmacologicClass**: `{'license': 'CC BY 4.0', 'identifier': 'N0000007568', 'class_type': 'Chemical/Ingredient', 'name': 'Oxazolidinones', 'source': 'FDA via DrugCentral', 'url': 'http://purl.bioontology.org/ontology/NDFRT/N0000007568'}`
- **SideEffect**: `{'license': 'CC BY-NC-SA 4.0', 'identifier': 'C1112256', 'name': 'Peripheral sensorimotor neuropathy', 'source': 'UMLS via SIDER 4.1', 'url': 'http://identifiers.org/umls/C1112256'}`
- **Symptom**: `{'license': 'CC0 1.0', 'identifier': 'D051346', 'name': 'Mobility Limitation', 'source': 'MeSH', 'url': 'http://identifiers.org/mesh/D051346'}`