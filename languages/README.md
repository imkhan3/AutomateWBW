# Translation languages

The Hadith generator always includes English. To make another language available,
add a `language_<code>.json` file in this folder, for example:

```json
{
  "code": "fr",
  "name": "French"
}
```

Use a unique lowercase two- or three-letter language code. The generator discovers
these files automatically and offers each language when creating a Hadith. Its
translation key is the language code, and that language appears in the generated
HTML controls when translations exist in the selected JSON.

The `add_<language>.py` scripts are optional commands for adding translations to
existing word-by-word JSON files.
