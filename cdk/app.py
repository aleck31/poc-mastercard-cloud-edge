#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.issuer_stack import IssuerStack

app = cdk.App()
IssuerStack(app, "poc-mastercard-cloud-edge", env=cdk.Environment(region="ap-southeast-1"))
app.synth()
