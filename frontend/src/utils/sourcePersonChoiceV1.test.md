# Source person choice regression

When a user enters a non-empty new-person name, that explicit create action must override any AI-suggested existing character. The frontend request must therefore send `character_id: null` and the trimmed `name` value.
