# Convert Google Keep notes to Bear notes

[Bear](https://bear.app) for iOS is an elegant Markdown-based notes app. I like it a lot more than Google Keep, and I love Google Keep. 

I wrote this script to convert a [Google Takeout](https://takeout.google.com/) export of an account's Keep notes into the correct format for Bear import.

I am putting this script up as-is, with no warranties. Use it at your own discretion. I may come back and add some more documentation but I think if you're already doing this process, you can probably figure it out.


**Requirements**

- Python 3.6+


**Usage:**

```
$ python3 keep2bear.py \
    -i <root directory of Google Takeout export> \
    -o <output directory>
```