class Planner:
    def __init__(self):
        pass

    # create_plan: Converts user request into a list of tasks
    def create_plan(self, user_input):
        # lowercase entire input for easier keyword detection
        text = user_input.lower()

        # LLM summary mode will be ON by default. Manual request will be needed to turn it off.
        use_llm_summary = True

        # Explicit user control over LLM summary mode
        if "no summary" in text:
            use_llm_summary = False
        elif "with summary" in text:
            use_llm_summary = True

        # Get tickers
        tickers = []
        # Tickers are in uppercase so convert entire request to upper case
        upper_text = user_input.upper()
        # Split input into tokens and remove commas
        tokens = upper_text.replace(",", " ").split()
        #Words that should NOT be treated as stock tickers
        # This prevents phrases like "WITH" or "SUMMARY" from being misread as symbols
        stop_words = {"ANALYZE","COMPARE","FOR","OVER","LAST","PAST","YEAR","YEARS","MONTH","MONTHS","AND", "THE", "PLEASE", "STOCK", "STOCKS", "ME", "MY", "WITH", "SUMMARY", "NO"}

        for token in tokens:
            # Remove any punctuations around the ticker
            cleaned_token = token.strip("()[]{}:;.!?\"'")
            # 1-5 characters
            if 1 <= len(cleaned_token) <= 5 and cleaned_token.isalpha() and cleaned_token not in stop_words:
                # Prevent duplication and maintain order
                if cleaned_token not in tickers:
                    tickers.append(cleaned_token)

        # Get period
        period = "1y" # default period

        words = text.split()
        for i, word in enumerate(words):
            # Look for patterns like "1 year" or "6 months" etc.
            if word.isdigit() and i + 1 < len(words):
                unit = words[i + 1]
                if "year" in unit:
                    period = f"{word}y"
                elif "month" in unit:
                    period = f"{word}mo"

        # Validate tickers
        # At least one ticker is required
        if len(tickers) == 0:
            raise ValueError("No valid ticker symbols found in input.")
        # System will take at most two tickers
        if len(tickers) > 2:
            raise ValueError("Please specify at most two tickers.")

        # Construct task plan
        tasks = []

        for ticker in tickers:
            # Get historical price data
            tasks.append({"task" : "fetch_data", "ticker" : ticker, "period" : period})
            # Calculate performance metrics
            tasks.append({"task" : "compute_metrics", "ticker" : ticker})
        # If exactly two stocks were provided, then compare them
        if len(tickers) == 2:
            tasks.append({"task" : "compare_metrics"})
        # Return both the task list and the LLM summary control flag
        return {"tasks": tasks, "use_llm_summary": use_llm_summary}
