# v0.7.2 - 30 Sep 2022
- Fix bug when config file is empty
- Disable caching for YASGUI
- Update YASGUI

# v0.7.1 – 19 Sep 2022
- Fix bug where sub-queries with constants where not considered for merging

# v0.7.0 – 17 Sep 2022
- Added feature to restrict the metadata collection of an endpoint to specific classes

# v0.6.4 – 16 Sep 2022
- Fix quoted special chars in query string

# v0.6.3 – 05 Sep 2022
- Added basic authentication with Base64 encoding

# v0.6.2 – 31 Aug 2022
- Add possibility to create configuration instance from JSON string
- Add method to save a configuration instance to file
- Update Python base image to 3.9.13 on bullseye

# v0.6.1 – 16 Aug 2022
- Fix a type hint for Python versions < 3.10
- Create config object on import of `DeTrusty.Molecule.MTCreation`
- Raise exceptions during metadata collection instead of just logging them
- Fix issue when using a list of endpoints and not a dictionary
- Prevent generation of parsetab.py
- Rename log from metadata creation to `.rdfmts.log`

# v0.6.0 – 13 Aug 2022
- Exclude tests from Docker image
- Fix loggers
- Update dependencies
- Add capability to query private knowledge graphs
- Update RDF Molecule Template creation
  - Collect metadata from private endpoints
  - Gather metadata from RML mappings
- Fix issue with non-ASCII characters in query 

# v0.5.1 – 27 Jul 2022
- Add checks (directory exists, file writeable) for the metadata output file before collecting the metadata
- Keep a list of all triple patterns in the decomposer
- Remove Flask from the list of dependencies of the library

# v0.5.0 – 26 Jul 2022
- Some changes in order to use DeTrusty as a library and a service

# v0.4.5 – 30 Jun 2022
- Fixed use of incorrect set of variables for OPTIONALs

# v0.4.4 – 14 Jun 2022
- Fixed request payload to work with the Wikidata endpoint (https://query.wikidata.org/sparql)

# v0.4.3 – 22 May 2022
- Fixed issue in response header when the SELECT clause included an asterisk (*) to retrieve all variables

# v0.4.2 – 21 May 2022
- Fix endpoint path behind proxy

# v0.4.1 – 20 May 2022
- Fix for joining sub-queries at remote source configuration

# v0.4.0 – 20 May 2022
- Web interface using YASGUI added
- Configuration for joining sub-queries at remote source

# v0.3.0 – 19 May 2022
- Support for VALUES clause
- Update of installation method
- Update of dependencies
- Support for new decomposition types
  - Triple-wise
  - Exclusive Groups

# v0.2.0 – 07 Feb 2022
- Support for SERVICE clause
- Minor fixes for the use as a service

# v0.1.0 – 17 Dec 2020
- First version of DeTrusty as a SPARQL 1.0 federated query engine