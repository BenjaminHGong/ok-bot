import language_tool_python

tool = language_tool_python.LanguageTool("en-US")


async def check_grammar(text):
    if len(tool.check(text)) > 0:
        correct_text = tool.correct(text)
        response = "Bruh, your grammar is trash.\n"
        response += "Original Text: " + text + "\n"
        response += "Text after correction: " + correct_text
        return response
    else:
        return False
