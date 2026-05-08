# PyPI Publication Consideration

## Current Status

Kanbanger is currently installed via:
```bash
pip install -e .
```

This requires cloning the repository or copying the distribution package.

## Should We Publish to PyPI?

### Benefits of PyPI Publication

#### 1. Easier Installation
```bash
# Current
git clone https://github.com/earlyprototype/kanbanger.git
cd kanbanger
pip install -e .

# With PyPI
pip install kanbanger
```

#### 2. Version Management
- Users can install specific versions
- `pip install kanbanger==2.0.0`
- `pip install kanbanger>=2.0.0,<3.0.0`
- Automatic dependency resolution

#### 3. Wider Distribution
- Listed on PyPI.org (discoverable)
- Appears in package search results
- Standard Python packaging
- Easier for enterprise adoption

#### 4. Simplified Updates
```bash
pip install --upgrade kanbanger
```

#### 5. Integration Benefits
- Works with `requirements.txt`
- Compatible with virtual environments
- Standard with poetry, pipenv, etc.
- Easier CI/CD integration

### Drawbacks of PyPI Publication

#### 1. Release Process Overhead
- Must create distributions (`sdist`, `wheel`)
- Upload to PyPI on each release
- Version number management critical
- Can't easily "unpublish" broken releases

#### 2. Name Availability
- Need to check if `kanbanger` is available on PyPI
- May need alternative name if taken

#### 3. Maintenance Commitment
- Expected to maintain stable releases
- Security updates need prompt releases
- Users expect professional support level

#### 4. Breaking Changes More Impactful
- Users depend on stable API
- Deprecation process needed
- Semantic versioning strictly required

#### 5. Distribution Package Still Needed
- Spec_Engine integration uses `kanbanger-dist/`
- Still need to maintain distribution folder
- Two distribution methods = more maintenance

## Current Use Cases

### 1. Direct Users (Developers)
**Current method works:** Clone and install locally
**PyPI benefit:** Moderate - easier initial setup

### 2. Spec_Engine Integration
**Current method optimal:** Copy `kanbanger-dist/` folder
**PyPI benefit:** Low - still need custom files (spec_engine_integration.py, etc.)

### 3. Enterprise/Team Deployments
**Current method challenging:** Requires git access and manual installation
**PyPI benefit:** High - standard package management

### 4. CI/CD Pipelines
**Current method:** Git clone or submodule
**PyPI benefit:** High - standard `pip install` in workflows

## Recommendation

### Phase 1: Not Yet (Current)
**Reasoning:**
- Still in active development (v2.0.0 just released)
- API not yet stable (features in backlog might require changes)
- Distribution package (`kanbanger-dist/`) is core to Spec_Engine integration
- Small user base (not yet proven at scale)
- Maintenance overhead not justified yet

**Continue with:**
- Git-based installation
- Distribution package for Spec_Engine
- Focus on feature stability

### Phase 2: Preparation (After ~3-6 months)
**When to consider PyPI:**
- API stabilises (breaking changes unlikely)
- User base grows (>50 stars, multiple forks)
- Feature set complete enough (bidirectional sync implemented)
- Documentation mature
- Multiple contributors active

**Preparation steps:**
1. Stabilise API (no breaking changes for 2+ releases)
2. Add automated tests (pytest suite)
3. Set up CI/CD (GitHub Actions)
4. Create comprehensive package metadata
5. Check PyPI name availability
6. Create test PyPI upload
7. Document release process

### Phase 3: Publication (Future)
**Trigger points:**
- Community requests PyPI distribution
- Enterprise adoption requires it
- Competing tools available on PyPI
- Integration with other tools needs it

**Publication checklist:**
- [ ] API stable for 3+ months
- [ ] Comprehensive test suite (>80% coverage)
- [ ] CI/CD with automated testing
- [ ] Documentation complete
- [ ] CHANGELOG maintained
- [ ] Security policy documented
- [ ] PyPI account created
- [ ] Package metadata polished
- [ ] Release automation scripted

## Alternative: GitHub Packages

Consider GitHub Packages as intermediate step:
- Easier than PyPI
- Still allows `pip install`
- GitHub-integrated
- Less commitment

```bash
pip install git+https://github.com/earlyprototype/kanbanger.git@v2.0.0
```

## Decision Matrix

| Factor | Current (Git) | PyPI | Weight |
|--------|--------------|------|--------|
| Ease of installation | 3/5 | 5/5 | High |
| Maintenance effort | 5/5 | 2/5 | High |
| Discoverability | 2/5 | 5/5 | Medium |
| Version control | 4/5 | 5/5 | Medium |
| Spec_Engine integration | 5/5 | 3/5 | High |
| Breaking change flexibility | 5/5 | 2/5 | High |
| Enterprise adoption | 2/5 | 5/5 | Medium |

**Current score: 26/35 (74%)**  
**PyPI score: 27/35 (77%)**

Close scores suggest **waiting** makes sense until clear advantage emerges.

## Immediate Action

**Recommendation: Defer PyPI publication**

Instead, focus on:
1. Stabilising current feature set
2. Growing user base organically
3. Gathering feedback on API design
4. Implementing key backlog features
5. Building test suite

**Revisit in:** Q2 2026 (approximately 3-6 months)

**Tracking:** Leave "Consider PyPI publication" in TODO as reminder

## If User Demand Emerges

If multiple users request PyPI:
1. Fast-track preparation steps
2. Create test PyPI upload
3. Gather feedback on package
4. Official PyPI release in minor version (v2.1.0)

## Documentation Note

Add to README:
```markdown
## Installation

### From Source (Recommended)
```bash
git clone https://github.com/earlyprototype/kanbanger.git
cd kanbanger
pip install -e .
```

### Direct from GitHub
```bash
pip install git+https://github.com/earlyprototype/kanbanger.git@v2.0.0
```

Note: PyPI publication planned for future release after API stabilisation.
```

---

## Summary

**Current decision: NOT publishing to PyPI**

**Rationale:**
- API still evolving
- Distribution package method works well
- Maintenance overhead not yet justified
- Flexibility for breaking changes valuable

**Revisit when:**
- API stable for 3+ months
- User base requests it
- Enterprise adoption requires it
- Backlog features implemented

**Alternative:** Document git-based installation clearly, consider GitHub Packages as intermediate step
