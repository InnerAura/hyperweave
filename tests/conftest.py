"""
Shared pytest fixtures for HyperWeave tests.

Provides common fixtures for ontology, generator, and test data.
"""

import pytest

from hyperweave.core.generator import BadgeGenerator
from hyperweave.core.ontology import OntologyLoader


@pytest.fixture(scope="session")
def ontology():
    """
    Session-scoped ontology loader.

    Loads ontology once per test session for performance.
    """
    return OntologyLoader()


@pytest.fixture
def generator(ontology):
    """
    Function-scoped badge generator.

    Creates a new generator instance for each test.
    """
    return BadgeGenerator(ontology)
