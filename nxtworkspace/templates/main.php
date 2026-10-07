<?php
script('nxtworkspace', 'main');
style('nxtworkspace', 'style');
?>

<div id="nxt-page">
    <div class="nxt-shell">

        <header class="nxt-header">
            <div class="nxt-brand">NXT AI</div>

            <h1>Turn Information into Insight</h1>

            <p>
                Ask questions about your files, policies, projects, and workspace information.
            </p>

            <div id="nxt-health" class="nxt-health nxt-health-checking">
                Checking AI system...
            </div>
        </header>

        <main id="nxt-chat" class="nxt-chat">

            <div id="nxt-messages" class="nxt-messages">

                <div class="nxt-welcome">
                    <img class="nxt-welcome-icon" src="<?php p(\OC::$server->getURLGenerator()->imagePath('nxtworkspace', 'app.svg')); ?>" alt="NXT AI">

                    <div class="nxt-welcome-title">
                        How can I help?
                    </div>

                    <div class="nxt-welcome-text">
                        Ask about documents, policies, projects, or information available in your workspace.
                    </div>
                </div>

            </div>

            <div id="nxt-sources" class="nxt-sources" hidden>
                <div class="nxt-sources-title">
                    Sources
                </div>

                <div id="nxt-sources-list"></div>
            </div>

            <form id="nxt-chat-form" class="nxt-input-area">

                <textarea
                    id="nxt-message"
                    rows="2"
                    placeholder="Ask NXT AI about your workspace..."
                    aria-label="Message"
                    required
                ></textarea>

                <button id="nxt-send" type="submit">
                    Send
                </button>

            </form>

        </main>

    </div>
</div>