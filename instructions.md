You are a python developer
We are starting a brand new project

The problem: after trips I have a lot photos, of which I want to select the best and the most descriptive ones to put into the album. At the moment I do this manually. I want to automate this process

Known knowns:
- project and dependencies should be managed by uv
- pytest for unit test
- I have access to local GPU
- I want to use cloud based model as "brain and eyes" to select best photos
- I want to create a deterministic way to preprocess and cluster photos or
- I want to use an open-source vision model to cluster photos more intellegently or
- both
- each day can have anywhere between 10 and 100 photos
- folder can contain photos (JPEG, JPR, PNG, HEIC) and videos and maybe other artifacts

Known unknowns:
- which cloud based model to use
- which open source model to use
- how exactly "deterministic" way will look like

### Project structure
**src** - where all logic will live. Create subfolders as needed
**tests** - where tests will live. Create subfolders for unit tests and other tests as needed
**planning_docs** - where we will plan the project into features and stories (like scrum)
**progress.md** - where you'll note your progress
**example_photos** - photos you can use as example for writing code and for tests
**.env** -  where keys for APIs will live

### Project parts

At the moment I can see these big parts for this project (in chronological order):
- filter out any blurry/dark photos or compromised in any other way, ignore videos or non-photo files
- organise all photos into folders by day, "day01", "day02" etc
- do preprocessing of photos per day (cluster into groups by similarity, like when there are a few shots of a the same person against the same background)
- select at most N best photos from each day and at most M photos in total for all days

### A more verbose project requirements and definitions
#### What "best" mean
A selection of photos per day that describe it in the most diverse way: shots with people on them (people who are supposed to be on them by design, not just passers by), shots of nature, cyties, animal etc. This definition can change, so needs to be located in place easily modifiable.
#### Example groups for clustering
- where person/people are the main objects (example: a photo of person with river on the background)
- cities (example: a perspective shot of a street (with or without people))
- architecture (example: a single building or monument)
- animals 
- food
This is not exhaustive list 

#### Logic for limits of photos
I want at most N photos per day and at most M photos in total. N and M must be configurable. 
Additional logic: some days might have less variability than others, so there might be significantly fewer shots than N. I want agnet to be intellegent, so that it can reallocate resources from such days into more eventful days. 
**Example**
Limit per day: 10
Limit in total: 100
Day 1 was arrival day, so only has 10 photos of which 2 are chosen as best. Day 2 was action day and has 100 photos, of which 15 are potentially best. How ever the limit per day is 10. Since the day before was not as eventful, it didn't use its limit so we can use these 8 shots to include more photos in the next days. As long as the total number per whole trip is not exceeding its limit (100 in this case)

NOTE: There can be days with 0 best shots

#### How should app function
I want to simply run the a script via VS Code to do the job. I want to be able to set path to photo folder before running it. This will be local agent.


### How do we work
- first identify features
- for each feature create stories to reach the feature
- write clean, readable code, with each part (filtering, preprocessing etc) having its own module and all configurations clearly visible in separate module too - prefer readability over saving number of lines
- write comments and docstrings
- implement logging
- keep features and stories in planning_docs
- note your progress in progress.md after completion of each new story and modify it whenever change occurs to existing code (e.g. fixing bug)
- NEVER really remove any photos or files. Within each day folder create a "rejected" folder and move low quality photos there
- within each day folder also create folder "not_photo" and move all videos and non-image files there.
- In the main photos folder, create "to_print" folder and move all chosen photos there. Inside "to_print", photos should also be sorted into days. Example structure of photos folder after agent is done with choosing photos:
/MyAwsomeTrip
│
├── to_print/                 
│   ├── day01
|   |   ├──photo0001
│   └── day02
|   |   ├──photo0001
│
├── day01/                  
│   ├── rejected/
│   ├── not_photo/
│   ├── photo0001          
│   └── photo0002
│
├── day02/                
│   ├── rejected/
│   ├── photo0001          
│   └── photo0002

### planning_docs
I want structure of this folder to be as follows:
Each epic we identify should should have its own folder with name of this format: "E<ID>_<short_name>", where <ID> is epic id - ingerer, incremented by 1, starting with 01 and <short_name> is a shortened version of epic name, like "initial_filtering" for epic "Filter out low quality photos".
Each epic will have a number of features associated with this epic, e.g. "Identify and remove blurry images", "Identify and remove dark images". Each feature, is structured as .json, with name of format: "F<ID>_<short_feature_name>", e.g. "F01_blurry_images". Feature json will have stories required to implement this feature. Json should be of this format:
```
{
    "FeatureId": "01",
    "FeatureName": "Identify and remove blurry images",
    "Description": "I want to identify images that are blurry and move them to 'rejected' folder, so that the model doesn't look at them when chosing best shots",
    "Stories":[
        {
            "StoryId": "01",
            "StoryName": "Identify blurry images",
            "StoryDescription": "Given folder with images of different type, identify blurry ones and return their files names as list."
            "AcceptanceCriteria": "Code returns list of blurry file names. Unit tests pass"
            "IsDone": false
        },
        {
            "StoryId": "02",
            "StoryName": "Remove blurry images",
            "StoryDescription": "Given list of blurry images file names, move respective files to 'rejected' folder. Create 'rejected' folder if not already existing."
            "AcceptanceCriteria": "Blurry images are moved from main folder for that day to 'rejected' folder for that day. Unit tests pass"
            "IsDone": false
        }
    ]
}
```

When you're done with a story, mark it is done by changig "IsDone" to true.


### progress.md
Always append to this file, never overwrite.
When adding progress, reference which epic, feature and story it is from.
Don't be too verbose, explain briefly what have you done.


### Testing
With completion of each story, write unit tests for functions you created. NEVER use real AI (like OpenAI) services for tests, always mock calls and return values. If you're using photos from example_photos for tests, add folder containing such photos to .gitignore. I don't want my photos to be publicly available.