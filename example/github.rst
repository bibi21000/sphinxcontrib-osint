﻿==========
GitHub
==========

GitHub
==========

.. osint:org:: github
    :label: Github
    :ident:
    :source:
    :url: https://github.com/

.. osint:event:: github_pages
    :label: GitHub Pages
    :source:
    :url: https://en.wikipedia.org/wiki/GitHub#GitHub_Pages
    :from: github
    :from-label: Launch
    :from-begin: 2001-01-01

.. osint:event:: github_pages_quickstart
    :label: GitHub Pages\nQuickstart
    :source:
    :url: https://docs.github.com/en/pages/quickstart
    :from: github
    :from-label: Quickstart

.. osint:quote::
    :label: Refer to
    :from: github_pages_quickstart
    :to: github_pages

.. osint:event:: github_connect_minneapolis
    :label: Connect\nMinneapolis
    :source:
    :url: https://resources.github.com/events/github-connect-minneapolis/
    :from: github
    :from-label: Organize
    :from-begin: 2025-06-05

.. osint:ident:: Thomas_Dohmke
    :cats: other
    :source:
    :label: Thomas Dohmke
    :link: https://www.linkedin.com/in/ashtom/
    :orgs: github

    He loves building products that make developers\' lives easier

.. osint:relation::
    :label: CEO
    :from: Thomas_Dohmke
    :to: github
    :begin: 2021-11-01


Microsoft
==========

.. osint:org:: microsoft
    :label: Microsoft
    :ident:

.. osint:ident:: sun
    :label: Sun\nMicrosystems
    :from: Satya_Nadella
    :from-label: worked
    :from-end: 2014-01-01

.. osint:ident:: Satya_Nadella
    :label: Satya Nadella
    :source:
    :url: https://fr.wikipedia.org/wiki/Satya_Nadella
    :orgs: microsoft
    :cats: other
    :to: microsoft
    :to-label: CEO
    :to-begin: 2014-02-04

    Born 19 August 1967

.. osint:relation::
    :label: Buy
    :from: microsoft
    :to: github
    :begin: 2018-10-26

.. osint:source:: microsoft_github_buy
    :label: Acquisition
    :url: https://en.wikipedia.org/wiki/GitHub#Acquisition_by_Microsoft

.. osint:event:: azure_events
    :label: Azure\nevents
    :source:
    :link: https://azure.microsoft.com/en-us/resources/events
    :from: microsoft
    :from-label: Organize

.. osint:event:: microsoft_pay_so_much_github
    :label: Microsoft Pay\nso Much for GitHub
    :description: Why Microsoft Is Willing to Pay So Much for GitHub
    :cats: financial
    :source:
    :link: https://hbr.org/2018/06/why-microsoft-is-willing-to-pay-so-much-for-github
    :from: microsoft
    :from-label: Concerned
    :begin: 2018-06-06

.. osint:link::
    :label: Concerned
    :from: github
    :to: microsoft_pay_so_much_github


Linkedin
==========

.. osint:event:: microsoft_linkedin
    :label: Microsoft\nbuy Linkedin
    :description: Microsoft to buy LinkedIn for $26.2 billion in its largest deal
    :source:
    :url: https://www.reuters.com/article/business/microsoft-to-buy-linkedin-for-262-billion-in-its-largest-deal-idUSKCN0YZ1FO/
    :from: microsoft
    :from-label: Buy
    :cats: financial

.. osint:quote::
    :from: microsoft_linkedin
    :to: microsoft_pay_so_much_github
    :label: cited in
