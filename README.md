# language-money-politics
Analysis of US Congress 115 (2017-2018) using data on proposed Bills, tweets of Representatives and lobbyist information.

## Data Sources
* Bills:
.* Bill text information was taken from https://www.congress.gov
.* Bill vote information was taken from https://github.com/unitedstates/congress/wiki/votes
* Tweets:
.* Tweets were taken from https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/UIVHQR
* Lobbyists:
.* API applied for at https://www.govinfo.gov/bulkdata, confirmation pending

## EDA
The vast majority of bills proposed did not make it to a vote. 13,557 bills were proposed of which 4111 were considered active. 349 bills made it to a vote with only 55 of those being voted on jointly. 

### Baseline Model
A first pass was made to determine whether it could be predicted if a bill would come to a vote. The features used in the baseline mode were:
* number of democratic cosponsors 
* number of republican cosponsors
* how many cosponsors withdrew
* the type of bill
* document embeddings for the text of the bill

The document embeddings were calculated using Spacy's built in word vectors from en_core_web_lg and aggregated over the entire document. 

Random undersampling was used to deal with the large class imbalance in the data after splitting 25% of the data for a test set.

Three models with baseline parameters were used to set baselines for future predictions:
* Logistic regression: test score 89.2%, f1-score (no vote) .94, f1-score (vote) .33
* Random forest: test score 81.4%, f1-score (no vote) .90, f1-score (vote) .18
* SGD Classifier: test score 91.4%, f1-score (no vote) .95, f1-score (vote) .37