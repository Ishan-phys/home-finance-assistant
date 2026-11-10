# Glossary

Plain-English meanings for the words the app uses. They are in alphabetical order.

**Account.** Somewhere your money sits or is owed: a savings account, a credit card, a fixed
deposit, a mutual fund, property. You add accounts in setup, and statements are uploaded into them.

**Alias.** See [stand-in](#s).

**Allowance (monthly).** The most you mean to spend in a month. It is optional. If you set one,
**Safe to spend** never shows more than what is left of it. Set it in **Settings**.

**Assistant.** The **Ask** panel. It answers questions about your money by looking figures up in
your books. See the [assistant guide](assistant.md).

**Base amount.** Cash you keep aside as an emergency cushion. **Safe to spend** never counts it.
Set it in **Settings**.

**Books.** Everything the app knows about one person's money: their accounts, transactions, rules
and settings. Each person has their own, and nothing is shared between people.

**Categorizer.** The part of the app that sorts a new transaction into a category. It tries your
rules first, then your past choices, then the model if you set a key.

**Category.** A bucket a transaction is sorted into, such as Groceries, Dining, Housing or Salary.
"Money out" categories are things you spend on. "Money in" categories are where money comes from.

**Closing balance.** The balance printed at the end of a statement. The app checks it against your
books, and a mismatch means a statement is missing.

**Docker.** The program that runs the app for you, so you do not install a database or any tools.

**Double-entry.** How the books are kept. Every transaction moves money *from* one place *to*
another and the two sides always add up. It is why the figures on every page agree.

**Gap.** A difference between a statement's balance and your books. It usually means a month is
missing. The Inbox says so as "… is short of its statement".

**Hash.** A scrambled form of your password that cannot be turned back into the password. The app
stores only the hash. See [Configuration](configuration.md#sign-in).

**Inbox.** The list of things the app could not settle by itself, each with its fix beside it.
The goal is an empty list.

**Ledger.** Another word for a person's books.

**Model.** The AI service that sorts transactions into categories and answers your questions. It
needs a **model key**. It never does arithmetic, and it never sees your name or account numbers.

**Model key.** A secret code (an API key) from OpenAI or Anthropic that lets the app use their
model. Set it in `.env`. See [Getting started, step 5](getting-started.md#step-5-decide-about-a-model-key-optional).

**Money in transit.** Money that has left one of your accounts for another, where the other side
has not been uploaded yet. It waits in the Inbox until it is matched.

**Narration.** The text your bank prints beside each transaction, such as "UPI-TEST CAFE-…". The
app removes personal details from it before storing it, and keeps the original encrypted.

**Net in, net out, saved.** For one month: **net in** is income plus cashback plus money people sent
you. **Net out** is spending plus money you sent to people. **Saved** is net in minus net out. Moving
money between your own accounts is none of these.

**Net worth.** Everything you own minus everything you owe. Credit card balances and loans reduce
it. Investments count at their latest market value.

**Own-account move.** Money that moved between your own accounts: a card bill paid from your bank, a
transfer to your other savings account, an investment purchase. It is neither spending nor income,
and appears as a **transfer**. The category is called **Own account or investment**.

**Payee.** Who a transaction was paid to, such as a shop. The app cleans up the bank's text to
get one.

**Person.** One owner of books. You can add more than one, each with their own accounts and
privacy names. **Delete person** removes one and everything in their ledger.

**Redaction.** Removing personal details (names, account and card numbers, phone numbers, UPI
handles) from a statement before anything is stored or sent anywhere.

**Refund.** Money coming back from a shop. It is listed apart from spending and is not netted off.

**Rule.** A saved instruction: "if the narration contains this text, use this category". Rules
run before any guessing, and the first matching rule wins. Make one by ticking **Always do this**
when you pick a category.

**Safe to spend.** Your cash and savings, minus the base amount you keep aside, minus what you owe
on credit cards, capped by your monthly allowance if you set one. Investments, deposits, property
and gold are never counted.

**Savings rate.** Saved as a percent of net in for a month.

<a id="s"></a>**Stand-in.** A made-up name, such as `Credit_Or_Loan_2`, that replaces the real name of
one of your accounts, banks or categories before anything is sent to the model. Your real names
are put back into the answer on your computer.

**Statement.** A file from your bank listing what happened in an account. See
[Statements](statements.md).

**Token.** A stable label such as `[PERSON:ab12]` that replaces a personal detail in a statement.
The same payee always gets the same token, so grouping still works. It cannot be turned back into
the detail.

**Transaction.** One movement of money from one place to another, such as "HDFC Savings → Dining".

**Transfer.** A transaction between two of your own accounts. See **own-account move**.

**Uncategorized.** A transaction the app could not sort. It waits in the Inbox for you to choose
a category.

**Value (by hand).** The worth you enter yourself for an account the app cannot read statements for,
such as a fixed deposit, property or gold. Update it with **Update value**. A change counts toward
net worth, not income.

**Volume.** The place Docker keeps your data on your computer. It survives stopping and restarting
the app. See [Configuration](configuration.md#your-data).
