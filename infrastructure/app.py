from aws_cdk import App, Aws

from stack import LokaFoldBasic

app = App()
LokaFoldBasic(app, "LokaFoldBasic")
app.synth()
