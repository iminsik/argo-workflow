# User Guide

This guide is for end users of the Argo Workflow Manager application.

## Overview

Argo Workflow Manager is a web-based interface for submitting, monitoring, and managing Argo Workflows. It provides an intuitive way to run and track workflow executions without needing to use command-line tools.

## Getting Started

### Accessing the Application

1. Open your web browser
2. Navigate to the application URL (provided by your administrator)
3. You should see the Argo Workflow Manager dashboard

## Features

### Dashboard

The main dashboard displays:
- **Task List**: All submitted workflows with their current status
- **Run Task Button**: Submit a new workflow
- **Refresh Button**: Manually update the task list

### Workflow Status

Workflows can have the following statuses:

- **Pending** (Yellow): Workflow is waiting to be processed
- **Running** (Blue): Workflow is currently executing
- **Succeeded** (Green): Workflow completed successfully
- **Failed** (Red): Workflow encountered an error

## Using the Application

### Submitting a Workflow

1. Click the **"Run Python Task"** button
2. A confirmation message will appear showing the workflow ID
3. The new workflow will appear in the task list

### Viewing Workflows

The task list automatically refreshes every 5 seconds. You can also manually refresh by clicking the **"Refresh"** button.

#### Task List Columns

- **ID**: Unique identifier for the workflow
- **Phase**: Current status of the workflow
- **Started**: When the workflow began execution
- **Finished**: When the workflow completed (if finished)
- **Created**: When the workflow was created

### Understanding Workflow Status

#### Pending

The workflow has been submitted but hasn't started processing yet. This is normal and usually brief.

#### Running

The workflow is actively executing. You can see when it started in the "Started" column.

#### Succeeded

The workflow completed successfully. Both "Started" and "Finished" timestamps will be shown.

#### Failed

The workflow encountered an error during execution. Check with your administrator or use Argo CLI for detailed error messages.

## Tips and Best Practices

### Monitoring Workflows

- The task list auto-refreshes every 5 seconds, so you'll see status updates automatically
- Use the Refresh button if you need immediate updates
- Workflows typically process quickly, but complex workflows may take longer

### Troubleshooting

#### Workflow Stuck in Pending

If a workflow stays in "Pending" status for a long time:
- This may indicate a system issue
- Contact your administrator
- Check if other workflows are processing normally

#### Workflow Failed

If a workflow fails:
- The status will show as "Failed" (red)
- Contact your administrator for detailed error logs
- You can submit the workflow again

#### Can't See Workflows

If the task list is empty:
- Ensure workflows have been submitted
- Check your network connection
- Try refreshing the page
- Contact your administrator if the issue persists

## Frequently Asked Questions

### Q: How long do workflows take to complete?

A: It depends on the workflow. Simple workflows may complete in seconds, while complex workflows can take minutes or hours.

### Q: Can I cancel a running workflow?

A: Currently, cancellation must be done through the Argo CLI or Kubernetes. This feature may be added to the UI in the future.

### Q: What happens if I submit multiple workflows?

A: Each workflow runs independently. You can submit multiple workflows and they will all appear in the task list.

### Q: How do I see workflow logs?

A: Detailed logs are available through the Argo CLI or Kubernetes. Contact your administrator for access.

### Q: Can I customize workflows?

A: Workflow definitions are managed by administrators. Contact them to request new workflow templates.

## Getting Help

### Support

- **Technical Issues**: Contact your system administrator
- **Feature Requests**: Submit through your organization's request system
- **Documentation**: Refer to Argo Workflows documentation for advanced features

### Additional Resources

- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- Your organization's internal documentation

## Keyboard Shortcuts

- **Refresh**: Click the Refresh button or wait for auto-refresh (5 seconds)

## Browser Compatibility

The application works best with:
- Chrome/Edge (latest versions)
- Firefox (latest versions)
- Safari (latest versions)

## Privacy and Security

- Workflow data is stored in your organization's Kubernetes cluster
- Access is controlled by your organization's authentication system
- Workflow logs may be retained according to your organization's policies

## Version Information

For version information, contact your administrator.

---

**Note**: This application is a management interface for Argo Workflows. For advanced workflow features, you may need to use the Argo CLI or Kubernetes directly.

