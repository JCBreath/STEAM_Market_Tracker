# STEAM Market Tracker
A Simple Web Crawler
### Usage
Run
```console
python SteamDataRetrieve.py
```

Enter your `keyword`, e.g. ak47  
List will be printed and written to *item_list.txt*  
  
### Game List  
CSGO  
Dota (not available right now) 
PUBG (not available right now)  

### Dependencies
* urllib3 (for python3)  
* lxml


### Note
There is a limit of Steam requests.
If http retrieve failed, wait for 12-24 hrs to reset the request count.

### Example

Search `bloodsport`
```
SCAR-20 | Bloodsport (Field-Tested),$1.19  
SCAR-20 | Bloodsport (Well-Worn),$1.29  
SCAR-20 | Bloodsport (Minimal Wear),$1.90  
SCAR-20 | Bloodsport (Factory New),$3.25  
MP7 | Bloodsport (Battle-Scarred),$3.59  
StatTrak\u2122 SCAR-20 | Bloodsport (Field-Tested),$4.29  
StatTrak\u2122 SCAR-20 | Bloodsport (Well-Worn),$4.31  
MP7 | Bloodsport (Field-Tested),$4.43
MP7 | Bloodsport (Well-Worn),$6.34
StatTrak\u2122 SCAR-20 | Bloodsport (Minimal Wear),$6.62
MP7 | Bloodsport (Minimal Wear),$8.71
StatTrak\u2122 SCAR-20 | Bloodsport (Factory New),$11.93
StatTrak\u2122 MP7 | Bloodsport (Battle-Scarred),$12.60
MP7 | Bloodsport (Factory New),$14.26
StatTrak\u2122 MP7 | Bloodsport (Field-Tested),$16.23
StatTrak\u2122 MP7 | Bloodsport (Well-Worn),$19.12
StatTrak\u2122 MP7 | Bloodsport (Minimal Wear),$32.29
AK-47 | Bloodsport (Field-Tested),$33.84
AK-47 | Bloodsport (Well-Worn),$33.95
AK-47 | Bloodsport (Minimal Wear),$36.56
AK-47 | Bloodsport (Factory New),$46.23
StatTrak\u2122 MP7 | Bloodsport (Factory New),$59.23
StatTrak\u2122 AK-47 | Bloodsport (Well-Worn),$89.08
StatTrak\u2122 AK-47 | Bloodsport (Field-Tested),$91.97
StatTrak\u2122 AK-47 | Bloodsport (Minimal Wear),$140.76
StatTrak\u2122 AK-47 | Bloodsport (Factory New),$209.40
```
